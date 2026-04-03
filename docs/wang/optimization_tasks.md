# 系统优化任务清单

基于：system_issues_and_design_gaps.md + log_audit_and_design_drift_report.md + 专家知识调研
日期：2026-04-04

---

## P0 — 系统可靠性（不修则不可用）

### T1: Task Phase Template

**问题：** TaskAgent 对所有任务使用同一个 SYSTEM_PROMPT，无 per-task 阶段约束。LLM 自由即兴，"展开"变成 8 个 Job 40 次 LLM 调用。

**目标：** 每种任务类型有明确的阶段序列，LLM 只能在当前阶段内操作。

**具体改动：**
1. `models/core.py` — Task model 加 `phase_template: Optional[str]` 字段
2. 定义 template 枚举：
   - `deploy_only` — 仅 DeployExpert，成功/失败后直接 complete
   - `produce_single` — EconomyExpert 单项生产，完成即 complete
   - `produce_then_use` — Phase A: EconomyExpert 生产 → Phase B: 使用（Recon/Combat/Movement）
   - `composite_phased` — 多步骤任务，每步有明确允许的 Expert + 转换条件
3. `adjutant/adjutant.py` — 创建 task 时根据命令类型注入 template
4. `task_agent/agent.py` — SYSTEM_PROMPT 动态化：追加当前 task 的 phase 约束段
5. 约束格式示例：
   ```
   [TASK PHASE POLICY]
   Template: deploy_only
   Allowed experts: DeployExpert
   Phases: deploy → verify → complete
   MUST NOT start Recon/Economy/Combat jobs for this task.
   MUST verify construction yard exists via query_world before completing as succeeded.
   ```

**验收：** "展开" 只创建 1 个 DeployExpert job，LLM 调用 ≤5 次。

---

### T2: Complete Task Hard Guard

**问题：** `complete_task(succeeded)` 无条件接受。LLM 在最后一个 Deploy ABORTED 时宣布 "succeeded"。

**目标：** 框架层拒绝不满足条件的 success 声明。

**具体改动：**
1. `task_agent/handlers.py` — `handle_complete_task()` 加前置检查
2. 检查逻辑根据 `task.phase_template` 决定：
   - `deploy_only`: query_world 确认 has_yard=true
   - `produce_single`: 确认 produced_count >= target（从最后的 Job signal 读取）
   - 通用: 至少有 1 个 Job succeeded 才允许 task succeeded
3. Guard 不通过 → 返回 tool result `{"error": "guard_failed", "reason": "no construction yard found"}`，LLM 收到后可重试或改 result=failed

**验收：** Task #001 场景不再虚假 succeeded。

---

### T3: Task→Player 通信工具

**问题：** TaskAgent 无法主动与玩家沟通。design.md §6 定义了 `task_info / task_warning / task_question / task_complete_report` 四种消息，均未实现。

**目标：** Task 执行期间可向玩家发消息、问问题。

**具体改动：**
1. `task_agent/tools.py` — 新增 `send_task_message` tool 定义：
   ```
   send_task_message(type: "info"|"warning"|"question", content: str,
                     options?: list[str], timeout_s?: float, default_option?: str)
   ```
2. `task_agent/handlers.py` — `handle_send_task_message()` 调 Kernel 转发
3. `kernel/core.py` — `forward_task_message()` → 推送到 Adjutant 和 WS
4. `adjutant/adjutant.py` — 收到 task_question 时注册 `pending_question`
5. `ws_server/server.py` — 新消息类型 `task_message` 推送到前端
6. 前端 ChatView — 渲染 task 消息（info/warning 直接显示，question 带选项按钮）

**验收：** Deploy 失败时 TaskAgent 可以问 "MCV 部署失败，是否换位置？"，玩家回复路由回 TaskAgent。

---

## P1 — 质量和效率

### T4: Conversation History 压缩

**问题：** TaskAgent conversation 无限增长。Task #001 从 4.6K 字符膨胀到 79K。SYSTEM_PROMPT (3.3K) 每轮重发。

**目标：** 控制 conversation 在合理范围内。

**具体改动：**
1. `task_agent/agent.py` — `_build_messages()` 实现滑动窗口：
   - 保留 system prompt + 最近 N 轮完整对话 (N=6)
   - 超出部分压缩为单条 summary message
2. 相同类型 signal 去重：连续 5 个 resource_lost → 单条 "resource_lost repeated ×5"
3. tool result 中大 payload（world_summary 完整 actor 列表）截断为摘要

**验收：** Conversation 最大不超过 20K 字符。

---

### T5: Signal 日志顺序修正

**问题：** `kernel/core.py:start_job()` 中 `_rebalance_resources()` 在 `job_started` 日志之前执行，导致 `resource_lost` 先于 `job_started`。6/8 jobs 受影响。

**目标：** LLM 看到的事件顺序符合因果逻辑。

**具体改动：**
1. `kernel/core.py:start_job()` — 将 `slog.info("Job started")` 移到 `_rebalance_resources()` **之前**
2. 或者在 `_build_messages()` 中对 recent_signals 做顺序修正：job_started 优先于同一 job 的 resource_lost

**验收：** 日志中 job_started 始终先于同 job 的 resource_lost。

---

### T6: Smart Wake — 无增量跳过 LLM

**问题：** 89% 的 TaskAgent 唤醒是 review_interval 定时轮询，无新信息也触发 LLM 调用。

**目标：** 无信息增量时跳过 LLM 调用。

**具体改动：**
1. `task_agent/agent.py` — wake 时检查：
   - 自上次 wake 以来是否有新 signal/event
   - 如果无新信息且所有 job 状态未变 → 跳过 LLM，直接 sleep
2. `game_loop/loop.py` — review_wake 标记 `trigger="review"` 以区分

**验收：** 无信息增量的 review wake 不触发 LLM 调用。Task #001 场景 LLM 调用从 40 降到 <15。

---

### T7: DeployExpert 验证

**问题：** DeployExpert 调 `deploy_units()` 后立即标记 SUCCEEDED，不验证 Construction Yard 是否出现。

**目标：** Deploy 有可靠的成功/失败判定。

**具体改动：**
1. `experts/deploy.py` — 不立即 SUCCEEDED，改为 `self.phase = "verifying"`
2. 后续 tick 中 query WorldModel 检查：
   - actor 列表中是否出现 category=building 的 Construction Yard
   - 原 MCV actor 是否消失
3. 验证成功 → SUCCEEDED；超时 (5s) 未见 yard → FAILED
4. FAILED 时 signal 包含 `recovery_hint: "MCV 仍存在，可重新部署"`

**验收：** Deploy 虚假成功消除。Live 测试中 Deploy 结果与游戏实际状态一致。

---

## P2 — 架构完善

### T8: Information Expert 首批实现

**问题：** design.md 定义了 Information Expert（ThreatAssessor、EconomyAnalyzer、MapSemantics），实际零实现。TaskAgent 只有粗粒度 world_summary。

**目标：** 实现至少 2 个 Information Expert，为 Task Context 提供结构化 facts。

**具体改动：**
1. `experts/info_base_state.py` — BaseStateExpert:
   - 输出：`has_yard`, `has_power`, `has_barracks`, `has_refinery`, `base_established`, `tech_level`
   - 更新频率：事件驱动（STRUCTURE_BUILT / STRUCTURE_LOST）
2. `experts/info_threat.py` — ThreatAssessor:
   - 输出：`threat_level`, `threat_direction`, `enemy_composition`, `our_advantage`
   - 更新频率：每 5s 或 ENEMY_DISCOVERED 事件
3. `task_agent/context.py` — ContextPacket 加 `runtime_facts: dict`，包含 Information Expert 输出
4. TaskAgent SYSTEM_PROMPT 可选引用 runtime_facts

**验收：** Deploy task 的 context 中有 `has_yard: false`，LLM 不需要猜。

---

### T9: OpenRA 知识补全

**问题：** `experts/knowledge.py` 已有 10 个单位/建筑的 hard facts（E1-E4, E7-E11）和 economy/recon/combat 集成。但缺少 soft strategy：开局模板、科技路线前置条件、放置策略。

**当前已完成：**
- ✅ P0 全部完成：低电恢复、队列阻塞、矿场经济包、雷达感知、侦察策略分级、无目标回退
- ✅ EconomyExpert: 6/6 knowledge items 集成
- ✅ ReconExpert: 4/4 knowledge items 集成
- ✅ CombatExpert: 1/1 集成
- ✅ ProductionAdvisor: 基础规则 + 车辆工厂检测
- ⚠️ UnitRegistry 有完整 cost/prerequisites 数据但 experts 未使用

**仍缺：**
1. 开局模板 (E14)：power → barracks → refinery → war factory 标准序列
2. 科技前置条件 (E15)：升科技前需要防御/经济覆盖
3. 放置策略 (E12)：建筑靠近矿区、扩张方向优化
4. UnitRegistry 数据利用：cost 数据用于优先级评分，prerequisites 用于可建性判断
5. 反制推荐：根据敌人构成推荐对应兵种

**具体改动：**
1. `experts/knowledge.py` — 新增：
   - `opening_template(faction)` → 返回标准开局序列
   - `tech_preconditions(target_tech)` → 返回前置条件清单
   - `counter_unit_for(enemy_type)` → 返回反制建议
2. `experts/planners.py` — ProductionAdvisor 使用开局模板和前置条件
3. `experts/knowledge.py` — 引入 UnitRegistry 数据：
   - `unit_cost(unit_type)` → 从 UnitRegistry 读取
   - `can_build(unit_type, current_buildings)` → 用 prerequisites 判断

**验收：** ProductionAdvisor 对空基地推荐 "power → barracks → refinery" 标准序列。

---

### T10: Adjutant 可观测性

**问题：** 整个 session 仅 2 条 Adjutant 日志。分类决策、路由逻辑、rule_match 过程完全不可见。

**具体改动：**
1. `adjutant/adjutant.py` — 在以下位置加 slog：
   - rule_match 尝试和结果
   - LLM classification 输入/输出
   - 路由决策（new_command / reply / query）
   - NLU legacy routing 决策
2. 目标日志量：每条玩家输入 3-5 条结构化日志

**验收：** 每条玩家输入在 Adjutant 组件下有完整的处理链日志。

---

## 依赖关系

```
T1 (Phase Template) ← T2 (Hard Guard)  — Guard 依赖 template 判断检查类型
T1 ← T6 (Smart Wake)                   — 有 phase 后才能判断"无增量"
T3 (Task→Player) 独立
T4 (Conversation 压缩) 独立
T5 (Signal 顺序) 独立
T7 (Deploy 验证) 独立
T8 (Info Expert) ← T1                  — runtime_facts 需要注入到 phase-aware context
T9 (知识补全) 独立
T10 (Adjutant 可观测性) 独立
```

**建议执行顺序：** T1 → T2 → T3 → T7 → T5 → T4 → T6 → T9 → T8 → T10
