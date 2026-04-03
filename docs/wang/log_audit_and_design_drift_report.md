# Log 系统审计与设计漂移定位报告

日期：2026-04-04
审计范围：logging_system、benchmark、Diagnostics、runtime 日志（session-20260401T190855Z）、design.md 对比

---

## 一、Log 系统审计结论

### 总体评分：8.5/10 — 基础设施优秀，工具层不足

Log 系统的 **基础架构** 设计良好、实现正确。结构化日志（slog）在所有核心组件中一致使用，持久化到 JSONL 文件，benchmark 跟踪完善，WS 推流到前端干净高效。

### 1.1 架构概览

```
slog (StructuredLogger)
  ├── LogStore (线程安全, 内存 + 磁盘双轨)
  │   ├── all.jsonl            # 全量时序日志
  │   ├── components/*.jsonl   # 按组件分流
  │   └── tasks/*.jsonl        # 按任务分流
  ├── BenchmarkStore (独立存储)
  │   ├── benchmark_records.json
  │   └── benchmark_summary.json
  └── WS Streaming → Frontend DiagPanel
      └── 过滤: DEBUG + benchmark → 不推, INFO+ → 推
```

**Session 目录结构：**
```
Logs/runtime/session-YYYYMMDDTHHMMSSZ/
├── session.json              # 元数据 (start/end/PID/counts)
├── all.jsonl                 # 全量 (14,277 entries)
├── components/               # 按组件分流
│   ├── kernel.jsonl
│   ├── task_agent.jsonl
│   ├── world_model.jsonl
│   ├── benchmark.jsonl
│   ├── expert.jsonl
│   ├── game_loop.jsonl
│   ├── adjutant.jsonl
│   └── main.jsonl
├── tasks/                    # 按任务分流
│   └── t_f2d56cd3.jsonl
├── benchmark_records.json
└── benchmark_summary.json
```

### 1.2 正确的部分

| 维度 | 状态 | 说明 |
|------|------|------|
| 统一 slog API | ✅ | 7 个核心组件全部使用 `get_logger(component)` |
| 标准字段 | ✅ | timestamp + iso_time + component + level + message + event + data |
| 磁盘持久化 | ✅ | Session-based JSONL，跨重启持久 |
| 按任务分流 | ✅ | tasks/ 目录自动按 task_id 归档 |
| Benchmark 分离 | ✅ | 独立存储，不污染主日志 |
| WS 过滤推流 | ✅ | DEBUG + benchmark 不推前端，INFO+ 推 |
| 时间戳全覆盖 | ✅ | 符合 design.md §7 "所有信息附带 timestamp" |
| Session 隔离 | ✅ | 每次运行独立目录，无碰撞 |

### 1.3 存在问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| 无离线 session 回放 | High | `replay()` 只查内存，无法加载历史 JSONL |
| queue_manager 组件名错误 | Medium | 日志记为 "kernel" 而非 "queue_manager" |
| GameAPI 无结构化日志 | Medium | openra_api/ 未接入 slog |
| WS server 无 slog | Low | 连接事件用 stdlib logger |
| UnitRegistry 无日志 | Low | 零日志输出 |
| Legacy .log 文件堆积 | Low | 41 个旧格式文件 (Dec 2025 - Mar 2026) 未清理 |
| 无日志轮转策略 | Low | Session 无限积累 |
| 无跨 session 分析 | Info | 各 session 孤立，无比较工具 |

### 1.4 design.md 合规性

**§7 要求：** "全流程 log + benchmark 框架：每步耗时记录，可查询，为优化准备"
→ ✅ 完全合规

**§7 要求：** "系统**所有信息**必须附带 `timestamp`"
→ ✅ 完全合规

**§7 要求：** "三区：Operations / Tasks / Diagnostics"
→ ⚠️ 前端有 DiagPanel，但后端无 Diagnostics 模块（仅有基础 query 函数）

---

## 二、Runtime 日志深度分析（session-20260401T190855Z）

### 2.1 Session 概览

| 指标 | 数值 |
|------|------|
| 时长 | 5 分 8 秒 |
| 总日志 | 14,277 条 |
| benchmark | 8,448 (59%) |
| world_model | 5,530 (39%) |
| task_agent | 204 (1.4%) |
| kernel | 38 (0.3%) |
| expert | 30 |
| game_loop | 20 |
| adjutant | 2 |
| main | 5 |

### 2.2 Task #001 ("展开") 关键数据

| 指标 | 数值 | design.md 期望 |
|------|------|------|
| LLM 调用 | **40** | 简单任务 2-3 |
| Job 创建 | 8 | 1 (DeployExpert) |
| Job 中止 | 7 | 0 |
| Wake 次数 | 19 | 2-3 |
| 运行时长 | 179.7s | 数秒 |
| 最终状态 | succeeded（虚假） | 应 failed 或 partial |
| Conversation 膨胀 | 80 msg, 79K 字符 | 应有压缩 |

### 2.3 Adjutant 日志分析

整个 session 仅 2 条 Adjutant 日志：
1. `player_input "展开"` → 接收输入
2. `input_classified command` → 分类为命令

**缺失的日志：**
- 无 rule_match 尝试记录
- 无 LLM classification 详情
- 无 task creation 路由记录
- Adjutant 日志量极低，可观测性不足

---

## 三、设计漂移定位（基于 runtime 日志证据）

### 漂移 1: Task Agent 应是"事件驱动监督者"，实际是"轮询 LLM 控制器"

**design.md §5：** "Brain 是事件驱动的监督者，不是逐帧控制器"
**design.md §4：** "事件驱动，不轮询。收到 Signal 才醒来。"

**runtime 证据：**
```
agent_wake: 19 次
  ├── agent_review_wake: 17 次 (89% — 定时轮询)
  └── signal-triggered:   2 次 (11% — 事件驱动)
```

19 次唤醒中 17 次是 `agent_review_wake`（10s 定时器触发），仅 2 次是 Signal 驱动。设计要求"收到 Signal 才醒来"，实际是持续轮询。

**根因：** review_interval=10s 定时器不区分是否有新信息。每次 wake 都触发完整 LLM 调用。

**影响：** 40 次 LLM 调用中大部分是无增量信息的冗余调用。

### 漂移 2: 简单任务应 2 次 LLM，实际 40 次

**design.md §9：** 探索地图任务"**总计 2 次** LLM 调用"
**design.md §10：** "部署基地车 → instant → start_job(DeployExpert) → 立即 complete_task"

**runtime 证据：**
```
Task: "展开" (应=deploy MCV)
LLM calls:  40
Jobs:       8 (1 Recon + 5 Deploy + 2 Movement)
Duration:   179.7s
```

"展开" 应该是一步操作（DeployExpert），但 LLM 将其解释为"战略扩张"，创建了 8 个不同类型的 Job。

### 漂移 3: Signal 顺序反直觉

**design.md §5：** Signal 是"面向决策的"，应帮助 LLM 理解因果关系。

**runtime 证据（6/8 jobs）：**
```
line 30: expert_signal resource_lost  job=j_76966359  ts=583.517
line 31: signal_routed resource_lost  job=j_76966359  ts=583.517
line 32: job_started                  job=j_76966359  ts=583.517  ← AFTER resource_lost
```

`resource_lost` → `signal_routed` → `job_started`。LLM 看到的因果链：Job 一出生就丢失资源。这在 5 个 DeployExpert job 上重复出现。

**根因：** `kernel/core.py:start_job()` 先调 `_rebalance_resources()`（可触发 resource_lost），后记 `job_started`。

### 漂移 4: 无 Task→Player 通信

**design.md §6：** "Task Agent 不直接给玩家发消息。通过结构化 API：task_info / task_warning / task_question / task_complete_report"

**runtime 证据：**
```
adjutant logs: 2 条 (input + classify)
task→player messages: 0 条
player questions asked: 0 条
```

Task #001 运行 180s，反复部署失败，从未告知玩家。整个 session 零条 task-to-player 消息。

**根因：** TaskAgent 工具集中无 `send_task_message` / `ask_player`。design.md 的 `TaskMessage schema` 和 `PlayerResponse schema` 均未实现。

### 漂移 5: Complete Task 无 Hard Guard

**design.md §10：** "部署基地车 → instant → start_job(DeployExpert) → 立即 complete_task"

**runtime 证据：**
```
line 240: task_completed  result="succeeded"
          summary="MCV successfully moved to and deployed at [64, 96]"

实际状态：
- 最后的 DeployExpert j_928437c2: ABORTED
- MovementExpert j_f394d608: 资源被回收
- Construction Yard: 不存在
```

LLM 在最后一个 Deploy 仍然 ABORTED 的情况下，宣布 "succeeded"。框架无条件接受了这个虚假 success。

### 漂移 6: Conversation 无压缩

**design.md §5：** "注入时机：task 启动全量 / Signal 触发 delta / 长时间无事件压缩摘要"

**runtime 证据：**
```
LLM input 第 1 轮:  2 msg,  4,593 字符
LLM input 第 40 轮: 80 msg, 79,225 字符
SYSTEM_PROMPT: ~3,330 字符 × 40 次重发 = 133,200 字符浪费
```

设计要求"Signal 触发 delta"和"压缩摘要"，实际每轮全量注入 + 完整历史回放。

### 漂移 7: Information Expert 零实现

**design.md §4：** "Information Expert（信息型）：只读，持续分析 WorldModel。包括 ThreatAssessor、EconomyAnalyzer、MapSemantics、EventDetector。WorldModel 就是一个 Information Expert。"

**代码证据：**
- `experts/base.py` 有 `InformationExpert` 基类
- 零个具体实现
- WorldModel 不以 Expert 身份运行
- 无订阅/取消订阅机制

### 漂移 8: Wake 驱动模型偏差

**design.md §5：**
```
唤醒（Signal / Event / 定时）
  → inject context packet
  → LLM 调用（带所有 tools）
  → LLM 返回 tool_use → 执行 tool → 结果回传给 LLM
  → LLM 可能继续调 tool
  → LLM 返回纯文本 → 本轮结束
  → sleep，等下一次唤醒
  → max_turns 限制（默认 10）
```

**runtime 证据：**
- 设计期望 1 次 wake 可能多轮 tool use 后结束
- 实际：每次 wake 只做 1-2 轮就产生一个 tool call，然后等下一次 review_wake
- 40 次 LLM 调用分布在 19 次 wake 中（平均 2.1 call/wake），但每次 wake 的信息增量很低

---

## 四、Benchmark 数据揭示的系统瓶颈

| Tag | Count | Avg (ms) | P95 (ms) | Max (ms) | Total (ms) |
|-----|-------|----------|----------|----------|------------|
| llm_call | 41 | 4,300.7 | 7,703.3 | 9,888.8 | 176,330.0 |
| world_refresh | 2,666 | 24.9 | 147.1 | 511.6 | 66,296.0 |
| job_tick | 2,724 | 25.4 | 147.7 | 893.6 | 69,220.7 |
| tool_exec | 2,706 | 0.017 | 0.003 | 3.1 | 45.4 |
| expert_logic | 14 | 2.5 | 13.1 | 31.8 | 35.1 |

**发现：**
- LLM 是唯一性能瓶颈：avg 4.3s，总耗时 176s（占 session 57%）
- world_refresh 和 job_tick 都在 25ms 以内，正常
- tool_exec 极快（0.017ms），说明工具层无阻塞
- 41 次 LLM 调用在 5 分钟 session 中消耗 176s，LLM 利用率 = 176/308 = 57%

**如果 LLM 调用从 40 降到 2（如 design.md 期望），总 LLM 耗时从 176s → ~8.6s，session 从 5 分钟降到 ~1 分钟。**

---

## 五、漂移优先级矩阵

| # | 漂移 | 严重度 | 影响 | 证据来源 |
|---|------|--------|------|----------|
| 1 | 无 Phase Policy → LLM 漂移 | P0 | 所有 managed task | Task #001 trace: 8 jobs, 40 LLM calls |
| 2 | Complete Task 无 Guard → 虚假 success | P0 | 系统可靠性 | Task #001 line 240: 虚假 succeeded |
| 3 | 无 Task→Player 通信 → 静默执行 | P0 | 玩家体验 | 0 条 task message |
| 4 | Conversation 无压缩 → token 膨胀 | P1 | 成本 + 质量 | 79K 字符 / 40 轮 |
| 5 | Signal 顺序反直觉 → LLM 误判 | P1 | agent 决策质量 | 6/8 jobs resource_lost < job_started |
| 6 | Review wake 主导 → 冗余 LLM 调用 | P1 | 性能 + 成本 | 89% wakes 是轮询 |
| 7 | Information Expert 零实现 | P2 | 架构完整性 | 代码审计 |
| 8 | Wake 驱动模型偏差 → 低效 | P2 | 效率 | 2.1 call/wake 但低增量 |

---

## 六、修复路线图

### 阶段 1: 止血 (P0)

1. **Phase Template 注入**
   - Task model 加 `phase_template` 字段
   - Adjutant 创建 task 时注入（deploy_only / produce_and_use / composite）
   - SYSTEM_PROMPT 动态化：根据 phase_template 限制允许的 Expert 和阶段转换

2. **Complete Task Hard Guard**
   - 框架级检查：deploy task 要求 has_yard=true
   - production task 要求 produced_count >= target
   - LLM 返回 succeeded 但 guard 不通过 → 拒绝并告知 LLM

3. **Task→Player 工具**
   - 实现 `send_task_message(type, content, options?)` tool
   - Kernel 转发给 Adjutant
   - 连接现有 `pending_questions` 和 `player_notification` 通道

### 阶段 2: 效率 (P1)

4. **Conversation Sliding Window**
   - 保留最近 N 轮 + 之前的摘要
   - 相同 signal 类型去重（5 个 resource_lost → "repeated resource_lost ×5"）

5. **Signal 顺序修正**
   - `start_job()` 中 `slog.info("job_started")` 移到 `_rebalance_resources()` 之前
   - 或在 context 中加高语义摘要覆盖底层时序

6. **Smart Wake**
   - review_wake 检查是否有新信息增量
   - 无增量 → 跳过 LLM 调用
   - 有增量 → 正常 wake

### 阶段 3: 完善 (P2)

7. **Information Expert 首批实现**
   - ThreatAssessor: 威胁等级 + 方向
   - MapSemantics: 资源区 + 要塞点

8. **Offline Session Replay**
   - 加载历史 JSONL → 内存 query
   - 跨 session 对比分析

9. **Adjutant 可观测性增强**
   - 补全 rule_match / classification / routing 日志
   - 当前仅 2 条，严重不足
