# Architecture Audit — 2026-04-01

Based on 6 rounds of live E2E testing + design.md cross-validation.

---

## 1. Bug 数量的本质：3 个结构缺陷，不是几十个独立 bug

12+ 个 live bug 归因到 3 个结构性缺陷：

### 缺陷 A：缺少 UnitRegistry 翻译层
- design.md §2 明确写了启动链 `GameAPI → UnitRegistry → WorldModel`
- UnitRegistry 从未实现
- 导致：名称不匹配、LLM 猜错 ID、阵营建筑混淆
- **修复方向**：在 WorldModel 或独立模块中实现 UnitRegistry，从 `OpenCodeAlert/mods/ra/rules/*.yaml` 加载

### 缺陷 B：EconomyExpert 对游戏队列语义理解不完整
- Mock 中 produce() 永远成功，live 中 auto_place 可能假成功、队列可能堵塞
- 导致：资源泄漏、完成时机错误、就绪建筑不计数、任务挂起
- **修复方向**：EconomyExpert 必须核验 WorldModel 中实际 actor 变化，不只信 API 返回值

### 缺陷 C：LLM 自由度过高 + 未实现能力暴露
- 简单命令（建造/生产）交给 LLM 自由选择 Expert，稳定性不够
- query_planner stub 暴露给 LLM，导致无效调用后行为漂移
- **修复方向**：高频简单命令走规则路由直接执行；未实现的 tool 不暴露

---

## 2. 阻塞根因

### GameLoop 阻塞 asyncio（已修）
- 根因：WorldModel.refresh() 用同步 socket 调 GameAPI，阻塞 event loop
- LLM（httpx async）和 WS 推送被饿死
- 修复：asyncio.to_thread() 下沉同步 I/O
- **设计漂移记录**：GameLoop 不再是纯单线程，worker thread 隔离已成事实

### 建造队列"卡住"（已修）
- 根因：auto_place_building 后游戏可能报成功但建筑没放下
- EconomyJob 信返回值 → 队列资源不释放 → 后续建造全部卡住
- 修复：核验 WorldModel 实际 actor 变化

---

## 3. NLU 规则路由架构（待实现）

### 当前
```
用户 → Adjutant(LLM 分类 ~2s) → Kernel → TaskAgent(LLM 选 Expert ~5s) → Job
```

### 目标
```
用户 → Adjutant(规则匹配 <10ms) → 命中 → 直接创建 Job → 完成后可选交 LLM 跟踪
                                  → 未命中 → 走 LLM 路径
```

### 规则匹配候选
| 模式 | Expert | Config |
|---|---|---|
| "部署基地车" / "deploy" | DeployExpert | query MCV actor_id |
| "建造{X}" where X in 建筑名 | EconomyExpert | queue_type=Building, unit_type=映射 |
| "生产N个{Y}" | EconomyExpert | count=N, unit_type=映射 |
| "探索" / "侦察" | ReconExpert | search_region=enemy_half |
| "战况如何" / query 关键词 | Adjutant 直接回答 | 不进 Kernel |

未命中的（"包围右边基地"、"修理后进攻"等复杂命令）继续走 LLM。

---

## 4. LLM 暴露审计

### TaskAgent LLM 工具列表

| Tool | 状态 | 风险 | 行动 |
|---|---|---|---|
| start_job | ✅ | 无 | 保留 |
| patch_job | ✅ | 无 | 保留 |
| pause_job | ✅ | 无 | 保留 |
| resume_job | ✅ | 无 | 保留 |
| abort_job | ✅ | 无 | 保留 |
| complete_task | ✅ | 无 | 保留 |
| create_constraint | ✅ | 无 | 保留 |
| remove_constraint | ✅ | 无 | 保留 |
| query_world | ✅ | 无 | 保留 |
| **query_planner** | **Stub** | **高** | **实现 Planner 或暂时移除** |
| cancel_tasks | ✅ | 无 | 保留 |

### System Prompt 内容
- 5 种 Expert config schema（完整字段+类型+允许值）
- 中英文命令→Expert 映射表
- 缺失："无目标时怎么办"的约束规则
- 缺失：阵营感知（苏联 vs 盟军建筑差异）

### Adjutant LLM
- 分类 LLM：只看 active_tasks + pending_questions + 最近 5 条对话，无 tool
- 查询 LLM：只看 world_summary + active_tasks，无 tool
- 风险低

---

## 5. 前端交互/同步问题

### 高严重度
| 问题 | 根因 | 影响 |
|---|---|---|
| WS 大帧无上限 | 前端没设 max_message_size | world_snapshot 超限静默断连 |
| 重连不清消息 | useWebSocket 不清理旧消息 | 用户分不清新旧状态 |
| 用户消息假回显 | 发送前就加到 UI | 发送失败时误导用户 |

### 中严重度
| 问题 | 根因 | 影响 |
|---|---|---|
| pending questions 不刷新 | task_list 用 fallback 保留旧值 | 已回答问题继续显示 |
| 无重连状态指示 | 缺少 UI 反馈 | 断连期间用户不知道 |
| benchmark 无限制 | DiagPanel 无 tag 限流 | 可能刷屏 |

---

## 6. 系统可观测性

### 当前盲区
| 层面 | 能看到 | 看不到 |
|---|---|---|
| GameAPI | 手动脚本查 | 无前端实时面板 |
| WorldModel | world_snapshot 推送 | 结构化不够 |
| Kernel | INFO 级日志 | 无结构化任务流程视图 |
| TaskAgent | tool call 日志 | **LLM reasoning（为什么选了这个 tool）** |
| 前端 | 日志+benchmark | 无 tag 过滤/限流 |

### 最大盲区
LLM 的决策过程不可见。只能看到调了什么 tool，看不到为什么。

---

## 7. 确认的设计漂移（需记入 design.md 或 dev_decisions）

| # | 漂移 | 原设计 | 实际 | 建议 |
|---|---|---|---|---|
| D1 | GameLoop 线程模型 | 单线程 10Hz | worker thread 隔离 I/O | 正式记录 |
| D2 | 简单命令路由 | 全量 LLM | 规则路由 + LLM 后跟踪 | 正式记录 |
| D3 | BASE_UNDER_ATTACK | auto Task → LLM | Kernel 直接起 CombatJob | 正式记录 |
| D4 | Planner | 设计存在 | runtime 需实现 | 分配实现 |
| D5 | 用户反馈语义 | 笼统 | 需区分：同步回执/异步通知/内部等待/真 blocker | 正式记录 |

---

## 8. Design.md 是 Bible — 执行原则

1. 所有实现必须对照 design.md，偏移需要明确记录理由
2. design.md 中未提及的能力不应暴露给 LLM
3. 简化是允许的（标记为"Phase N+"），但不能悄悄偏移
4. live 测试是验证是否符合 design 的唯一标准，mock 只做回归
