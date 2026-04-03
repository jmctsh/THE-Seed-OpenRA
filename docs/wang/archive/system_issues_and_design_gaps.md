# 系统问题与 Agent 设计缺口报告

日期：2026-04-04
基于：Yu 的 `task_agent_prompt_runtime_report.md` + 代码审计 + design.md 对比

## 核心判断

Task #001 ("展开") 40 次 LLM 调用、8 个 Job、180s 仍虚假 success — 这不是模型问题，是 **agent 框架对模型太不友好**。当前系统在 prompt 约束、context 质量、signal 语义、success guard 四个层面都有结构性缺口。

---

## 一、Agent 设计不完整清单

### 1.1 [Critical] Task 无 Phase Policy

**design.md 期望：** Task Agent 理解多步骤任务的阶段顺序
**现状：** SYSTEM_PROMPT 固定，对所有任务类型一视同仁。无 per-task phase template。

**后果：**
- "展开" 被过度解释为"战略扩张"，先侦察再部署（应直接 deploy）
- "整点步兵，探索地图" 7 个 Job 交叉漂移（barr→infantry→proc→recon→jeep→warf）
- LLM 在自由空间中做即兴规划，每次结果不同

**缺失代码：**
- `Task` model 无 `phase` 字段
- `Adjutant` 创建 task 时不注入 phase metadata
- 无 `task_template` 概念

### 1.2 [Critical] 无 Task-to-Player 对话工具

**design.md 期望（§6）：** Task Agent 通过 `task_info / task_warning / task_question / task_complete_report` 与玩家对话，经 Adjutant 转发。

**现状：** TaskAgent 11 个 tools 中无任何玩家通信工具：
```
start_job, patch_job, pause_job, resume_job, abort_job,
complete_task, create_constraint, remove_constraint,
query_world, query_planner, cancel_tasks
```

**后果：**
- 任务执行期间对玩家完全静默
- 无法问玩家 "MCV 反复部署失败，要换位置吗？"
- 只能通过 complete_task 的最终 summary 间接沟通
- design.md 的 `TaskMessage schema` 和 `PlayerResponse schema` 未实现

### 1.3 [Critical] Context 缺乏结构化 Runtime Facts

**design.md 期望（§5）：** context packet 包含 jobs 的 phase、resources、config。
**现状：** ContextPacket 只有 6 个原始 dict 字段：task, jobs, world_summary, recent_signals, recent_events, open_decisions。

**缺失的关键信息：**
- `has_yard: bool` — 部署是否成功
- `mcv_present: bool` — MCV 是否存在
- `deploy_confirmed: bool` — 部署是否被确认
- `retry_count: int` — 同类失败次数
- `phase: str` — 当前任务阶段
- `base_established: bool` — 基地是否建立
- `available_information_sources: list` — 可用信息源

LLM 只能从粗粒度 world_summary 和零散 signal 中自己推断，导致大量"猜测-验证"循环。

### 1.4 [High] 无 Information Expert / 信息订阅层

**design.md 期望（§4）：** Information Expert 是三种 Expert 类型之一。WorldModel 本身就是一个 Information Expert。ThreatAssessor、EconomyAnalyzer、MapSemantics 都是 Information Expert。

**现状：**
- `InformationExpert` 基类存在于 `experts/base.py`
- 但 **零个 Information Expert 被实现**
- WorldModel 提供 `world_summary` 但不以 Expert 身份运行
- 无订阅/取消订阅机制
- 所有任务共用同一个固定的 context 格式

### 1.5 [High] Conversation History 无压缩/修剪

**代码位置：** `task_agent/agent.py:_build_messages()`

```python
messages.extend(self._conversation)  # 无限增长
messages.append(context_msg)
self._conversation.append(context_msg)
```

**Task #001 实测数据：**
- 第 1 轮：2 条 message, ~4,593 字符
- 第 40 轮：80 条 message, ~79,225 字符
- SYSTEM_PROMPT（~3,330 字符）每轮重发

无滑动窗口、无摘要压缩、无相似 signal 去重。后期 context 中 90% 是重复信息。

### 1.6 [High] DeployExpert 无验证、Fire-and-Forget

**代码：** `experts/deploy.py`
- 调 `game_api.deploy_units()` → 立即 `self.status = JobStatus.SUCCEEDED`
- 注释承认 "GameAPI deploy may silently fail"
- 无后续验证 construction yard 是否出现
- 将验证责任推给 TaskAgent，但 TaskAgent 无 phase policy 要求验证

### 1.7 [Medium] Signal 日志顺序反直觉

**代码：** `kernel/core.py:start_job()`
```
→ _rebalance_resources()  → 可触发 resource_lost signal
→ slog.info("job_started")  → 日志在后
```

LLM 和人类看到的时序：先 `resource_lost`，后 `job_started`。导致 agent 误以为 Job 一出生就失败。这在 Task #001 中反复出现于 5 个 DeployExpert job。

### 1.8 [Medium] Planner Expert 只有 ProductionAdvisor

**design.md 期望（§4）：** ReconRoutePlanner、AttackRoutePlanner、ProductionAdvisor。
**现状：** 只实现了 ProductionAdvisor (f95b049)。侦察路线和进攻路线规划缺失。

### 1.9 [Medium] Complete Task 无 Hard Guard

**现状：** `complete_task` tool 无条件接受 LLM 的 `succeeded` 判定。无框架级 guard 如：
- "deploy task 要求 has_yard=true 才能 succeeded"
- "production task 要求 produced_count >= target 才能 succeeded"

LLM 可以在无证据时宣布 success（Task #001 step 40 的实际行为）。

---

## 二、已修复 vs 仍存在

| 问题 | 来源 | 状态 | 说明 |
|------|------|------|------|
| Rule routing 绕过 LLM | Yu报告 | ✅ 已修 | c82a6ab — 简单命令直接 Kernel |
| Deploy 无 MCV 短路 | Live Round 7 | ✅ 已修 | 076db78 — pre-check 立即返回 |
| Rule-routed task LLM 漂移 | Live Round 7 | ✅ 已修 | c2defff — monitor-only mode |
| Recon 永不终止 | Live Round 7 | ✅ 已修 | edf659d — 超时→partial |
| 资源泄漏 | Live Round 6 | ✅ 已修 | 72b535f — 终态释放 |
| Building chain 7层 bug | Live Round 6 | ✅ 已修 | 多个 commit |
| Game reset 清理 | Live Round 7 | ✅ 已修 | 770c2e6 |
| Queue Manager | pending_drift | ✅ 已修 | 76aa5fd — QueueManager |
| NLU 接入 | 用户需求 | ✅ 已修 | 1d64301 + 0925062 |
| Phase Policy 缺失 | Yu报告 §1.2 | ❌ 未修 | 无 per-task template |
| Task→Player 对话 | Yu报告 §7 | ❌ 未修 | 无 send_task_message tool |
| Context 结构化 facts | Yu报告 §3 | ❌ 未修 | 仍是原始 dict |
| Information Expert | design.md §4 | ❌ 未修 | 零实现 |
| Conversation 压缩 | Yu报告 §6 | ❌ 未修 | 无限增长 |
| Deploy 验证 | Yu报告 §4.3 | ❌ 未修 | fire-and-forget |
| Signal 顺序 | Yu报告 §5 | ❌ 未修 | resource_lost < job_started |
| Complete task guard | Yu报告 §10 | ❌ 未修 | 无条件接受 |
| Composite task drift | pending_drift §2 | ❌ 未修 | 无 bounded phase template |
| EconomyJob abort cleanup | pending_drift §6 | ❌ 未修 | abort 不清理队列 |

---

## 三、问题优先级排序

### P0 — 不修则系统不可靠
1. **Phase Policy + Composite Task Template** — 所有非 rule-routed 任务都会漂移
2. **Complete Task Hard Guard** — LLM 可无证据 success
3. **Task→Player 对话工具** — 设计核心能力缺失

### P1 — 显著影响质量
4. **Context 结构化 Runtime Facts** — 减少 LLM 猜测循环
5. **Conversation History 压缩** — 控制 token 膨胀（79K 字符/task 不可持续）
6. **DeployExpert 验证** — fire-and-forget 不可信

### P2 — 完善设计
7. **Information Expert 实现** — ThreatAssessor、MapSemantics
8. **Signal 日志顺序** — 修正 start_job 中 rebalance 与 log 的顺序
9. **更多 Planner Expert** — ReconRoutePlanner、AttackRoutePlanner
10. **EconomyJob abort 队列清理**

---

## 四、修复建议路径

**Phase A: Task Agent 收紧（P0）**
1. 给 Task model 加 `phase_template: Optional[str]` 字段
2. Adjutant 创建 task 时根据命令类型注入 template（deploy_only / produce_then_use / composite_phased）
3. SYSTEM_PROMPT 动态注入当前 task 的 phase 约束
4. complete_task 加 guard：根据 task type 检查硬条件
5. 实现 `send_task_message` / `ask_player` tool

**Phase B: Context 质量（P1）**
6. ContextPacket 加 `runtime_facts: dict`（has_yard, mcv_present 等）
7. 实现 conversation sliding window（保留最近 N 轮 + 摘要）
8. DeployExpert 加 verification tick（查 construction yard）

**Phase C: 架构完善（P2）**
9. 实现第一批 Information Expert
10. 修正 start_job 中 signal 与 log 的顺序
11. 实现更多 Planner Expert
