# 系统优化任务清单

日期：2026-04-04（v2 — 信息优先，不做行为约束）

核心原则：**Task Agent 的决策问题通过提供充足信息解决，不通过行为约束或权限限制。** 信息充分的 agent 自然会做出正确决策；信息不足时应主动问玩家。

---

## P0 — 信息质量（根因）

### T1: 结构化 Runtime Facts 注入

**问题：** TaskAgent 只有粗粒度 world_summary（economy/military/map/known_enemy），缺少关键决策信息。"展开" 时 LLM 不知道场上只有一个 MCV、没有基地、没有任何建筑，所以把"展开"理解成"战略扩张"去做侦察。

**正确行为：** 如果 context 告诉 LLM "你有 1 个 MCV，0 个建筑，0 个其他单位"，它自然知道"展开"就是 deploy MCV。如果基地已展开但不清楚展开什么，它自然会问玩家。

**目标：** 每次 wake 时 context 包含结构化的、面向决策的 runtime facts。

**具体改动：**
1. `task_agent/context.py` — ContextPacket 新增 `runtime_facts: dict`，包含：
   ```python
   runtime_facts = {
       # 基地状态
       "has_construction_yard": bool,
       "has_power": bool,
       "has_barracks": bool,
       "has_refinery": bool,
       "has_war_factory": bool,
       "has_radar": bool,
       "tech_level": int,           # 0=无基地, 1=yard, 2=有生产, 3=有科技

       # 关键单位
       "mcv_count": int,
       "mcv_idle": bool,            # MCV 存在且空闲
       "harvester_count": int,

       # 资源
       "can_afford_power_plant": bool,
       "can_afford_barracks": bool,
       "can_afford_refinery": bool,

       # 任务相关
       "active_task_count": int,
       "this_task_jobs": [{"job_id", "expert_type", "status", "phase"}],
       "failed_job_count": int,      # 本 task 内已失败的 job 数
       "same_expert_retry_count": int, # 同类型 Expert 连续重试次数
   }
   ```
2. `world_model/core.py` — 新增 `compute_runtime_facts()` 方法，从 actors + economy 计算上述 facts
3. `task_agent/agent.py` — `_build_context()` 时调用并注入 runtime_facts
4. SYSTEM_PROMPT 告诉 LLM："runtime_facts 是精确的结构化状态，优先参考这些而非从 world_summary 推断"

**验收：**
- "展开" + MCV 存在 + 无 yard → LLM 第一步直接 query_world 找 MCV → DeployExpert
- "展开" + 已有 yard + 无可 deploy 单位 → LLM 问玩家"展开什么？"
- LLM 调用次数从 40 降到 <10

---

### T2: Task→Player 通信工具

**问题：** TaskAgent 无法主动与玩家沟通。信息不足时无法问、执行出错时无法说。design.md §6 定义了 task_info / task_warning / task_question / task_complete_report 四种消息，均未实现。

**目标：** Task 执行期间可向玩家发消息、问问题。信息不足时主动问而不是猜。

**具体改动：**
1. `task_agent/tools.py` — 新增 `send_task_message` tool：
   ```
   send_task_message(type: "info"|"warning"|"question", content: str,
                     options?: list[str], timeout_s?: float, default_option?: str)
   ```
2. `task_agent/handlers.py` — `handle_send_task_message()` 调 Kernel 转发
3. `kernel/core.py` — `forward_task_message()` → 推送到 Adjutant 和 WS
4. `adjutant/adjutant.py` — 收到 task_question 时注册 pending_question
5. `ws_server/server.py` — 新消息类型 task_message 推送到前端
6. 前端 ChatView — 渲染 task 消息（info/warning 直接显示，question 带选项按钮）
7. SYSTEM_PROMPT 增加引导："当你不确定玩家意图时，使用 send_task_message(question) 询问"

**验收：** "展开" 在歧义场景下 TaskAgent 问 "你是要展开基地车，还是别的？"，玩家回复路由回 TaskAgent。

---

### T3: DeployExpert 结果验证

**问题：** DeployExpert 调 deploy_units() 后立即标记 SUCCEEDED，不验证 Construction Yard 是否实际出现。这不是权限问题——是信息回馈问题，Expert 自己都不知道自己是否成功。

**目标：** Deploy 有可靠的成功/失败信息反馈。

**具体改动：**
1. `experts/deploy.py` — 不立即 SUCCEEDED，改为 `self.phase = "verifying"`
2. 后续 tick 中 query WorldModel：
   - 检查是否出现 category=building 的 Construction Yard
   - 检查原 MCV actor 是否消失
3. 验证成功 → SUCCEEDED（signal 含 yard actor_id）
4. 超时 5s 未见 yard → FAILED（signal 含 "deploy_command_sent_but_no_yard_appeared"）

**验收：** Deploy 结果与游戏实际状态一致。TaskAgent 收到的 signal 是准确的。

---

## P1 — 效率和质量

### T4: Conversation History 压缩

**问题：** TaskAgent conversation 无限增长。Task #001 从 4.6K 字符膨胀到 79K。后期 90% 是重复信息，LLM 在噪声中做决策。

**目标：** 控制 conversation 在合理范围内，提高信息密度。

**具体改动：**
1. `task_agent/agent.py` — `_build_messages()` 实现滑动窗口：
   - 保留 system prompt + 最近 N 轮完整对话 (N=6)
   - 超出部分压缩为单条 summary message
2. 相同类型 signal 去重：连续 5 个 resource_lost → "resource_lost repeated ×5"
3. tool result 中大 payload（完整 actor 列表）截断为摘要

**验收：** Conversation 最大不超过 20K 字符。

---

### T5: Signal 日志顺序修正

**问题：** `kernel/core.py:start_job()` 中 `_rebalance_resources()` 在 `job_started` 日志之前执行，导致 LLM 看到 resource_lost 先于 job_started。信息顺序错误 = 给 LLM 错误的因果链。

**目标：** LLM 看到的事件顺序符合因果逻辑。

**具体改动：**
1. `kernel/core.py:start_job()` — 将 `slog.info("Job started")` 移到 `_rebalance_resources()` **之前**
2. 或者：在 context 构建时对 recent_signals 排序，job_started 优先于同 job 的 resource_lost

**验收：** 日志中 job_started 始终先于同 job 的 resource_lost。

---

### T6: Smart Wake — 无增量跳过 LLM

**问题：** 89% 的 TaskAgent 唤醒是 review_interval 定时轮询，无新信息也触发 LLM 调用。浪费 token 且无决策价值。

**目标：** 无信息增量时跳过 LLM 调用。

**具体改动：**
1. `task_agent/agent.py` — wake 时检查：
   - 自上次 wake 以来是否有新 signal/event
   - 如果无新信息且所有 job 状态未变 → 跳过 LLM，直接 sleep
2. `game_loop/loop.py` — review_wake 标记 `trigger="review"` 以区分

**验收：** 无信息增量的 review wake 不触发 LLM 调用。LLM 调用从 40 降到 <15。

---

## P2 — 架构完善

### T7: Information Expert 实现

**问题：** design.md 定义了 Information Expert（ThreatAssessor、EconomyAnalyzer、MapSemantics），实际零实现。T1 的 runtime_facts 是快速方案，Information Expert 是完整架构。

**目标：** 实现至少 2 个 Information Expert，持续分析 WorldModel 产出派生信息。

**具体改动：**
1. `experts/info_base_state.py` — BaseStateExpert:
   - 输出：has_yard, has_power, tech_level, base_established
   - 事件驱动更新
2. `experts/info_threat.py` — ThreatAssessor:
   - 输出：threat_level, threat_direction, enemy_composition
   - 定期 + ENEMY_DISCOVERED 事件更新
3. 注册到 WorldModel 或独立运行，产出通过 context 注入 TaskAgent

**验收：** TaskAgent context 中有来自 Information Expert 的派生分析数据。

---

### T8: OpenRA 知识补全

**问题：** experts/knowledge.py 已有基础 hard facts (P0 全部完成)，缺 soft strategy。

**当前已完成：** 低电恢复、队列阻塞、矿场经济包、雷达感知、侦察策略分级、无目标回退、车辆工厂检测。

**仍缺：**
1. 开局模板 (E14)：power → barracks → refinery → war factory 标准序列
2. 科技前置条件 (E15)：升科技前需要防御/经济覆盖
3. 放置策略 (E12)：建筑靠近矿区
4. UnitRegistry 数据利用：cost 用于评分，prerequisites 用于可建性判断
5. 反制推荐：根据敌人构成推荐对应兵种

**具体改动：**
1. `experts/knowledge.py` — 新增 opening_template / tech_preconditions / counter_unit_for
2. `experts/planners.py` — ProductionAdvisor 使用开局模板
3. 引入 UnitRegistry 的 cost/prerequisites 数据

**验收：** ProductionAdvisor 对空基地推荐标准开局序列。

---

### T9: Adjutant 可观测性

**问题：** 整个 session 仅 2 条 Adjutant 日志。分类决策、路由逻辑完全不可见。

**具体改动：**
1. `adjutant/adjutant.py` — 在 rule_match、LLM classification、路由决策、NLU routing 位置加 slog
2. 目标：每条玩家输入 3-5 条结构化日志

**验收：** 每条玩家输入在 Adjutant 组件下有完整处理链日志。

---

## 依赖关系

```
T1 (Runtime Facts) — 独立，最高优先
T2 (Task→Player 通信) — 独立，与 T1 互补（信息不足时问）
T3 (Deploy 验证) — 独立
T4 (Conversation 压缩) — 独立
T5 (Signal 顺序) — 独立
T6 (Smart Wake) — 独立
T7 (Info Expert) — T1 的架构完善版
T8 (知识补全) — 独立
T9 (Adjutant 可观测性) — 独立
```

**建议执行顺序：** T1 → T2 → T3 → T5 → T4 → T6 → T8 → T7 → T9
