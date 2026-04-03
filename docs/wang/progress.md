# Wang — Progress Log

## [2026-03-29 03:15] DONE — Session bootstrap and MCP issue diagnosis
- Set up agent directory (docs/wang/)
- Discovered MCP server agent-chat is not connected (mcpPresent: false)
- Root cause: agent-up script doesn't properly attach MCP stdio server to Claude process
- Established curl REST API fallback for communication
- Saved workaround to memory and agents.md
- Notified ac-topleader (msg_86232) about systemic MCP missing issue for remote agents
- ac-topleader confirmed bug (msg_86233): agent-up writes .mcp.json but claude CLI launch doesn't pass --mcp-config flag. Fix tracked.
- ac-topleader (msg_86237): MCP fix landed on master (c21f6d6). New agents will get MCP attached automatically. Current session still uses curl fallback.

## [2026-03-29 03:25] DONE — MCP reconnected after restart
- MCP server agent-chat now connected and all 5 tools working natively
- Root cause correction: MCP was manually disabled by user in MCP dialog, NOT a systemic agent-up bug
- Sent correction to ac-topleader (msg_86246) — false alarm apology

## [2026-03-29 05:50] DONE — Phase 0 系统调查与架构分析
- 完成代码库全面探索（Agent 发起 Explore）
- 产出 `docs/wang/architecture_analysis.md`：现状摘要、缺失清单、5个决策点、分层架构提案、代码映射表
- 分配 yu 3个深度调查任务（Job系统、IntelService、Agent接口）
- yu 完成报告 `docs/wang/yu_investigation_report.md`，核心发现：
  - 两套 Intel 栈并行且不统一
  - CombatAgent.company_states 是 ExecutorInstance 最佳参考
  - EconomyEngine.decide() 天然是 Planner 模式
  - Job 系统是执行基座，不是 Kernel
- 分配 yu 跟进任务：专家契约 ABC 草稿 + Intel 合并分析
- 更新架构分析文档整合 yu 发现

## [2026-03-29 06:00] DONE — yu 交付专家契约 + Intel 合并分析
- expert_contracts_draft.py: 统一 bind→start→tick→status→release 生命周期
- intel_merge_analysis.md: 两栈对比、facade 方案、4 阶段迁移
- wang/yu 对齐 4 个设计问题（proposal-first, abort vs release, ConcurrencyPolicy, str resource ID）

## [2026-03-29 06:10] DONE — 用户方向修正，重大调整
用户拍板：
- Kernel 无循环，被动仲裁器，Task 自己拥有循环
- 全部可重写，不需要增量兼容
- WorldModel/IntelService 都是观察型专家系统，需要改造
- 需要加入大量传统 RTS AI 技术（BT/FSM/GOAP/影响力图等）— roadmap 此处太草率
- 需要一个好的看板/dashboard
- 核心痛点深化："包围"例子——LLM 只会坐标偏移，不会真正的地形分析/兵力分配/时间协调
- 已更正 architecture_analysis.md 中的 3 个决策（Kernel/WorldModel/重写）
- 已分配 yu 进行传统 RTS AI 深度互联网调研 (msg_86301)

## [2026-03-29 07:40] DONE — 传统 RTS AI 调研整合 + 架构 v2
- yu 完成 rts_ai_research.md：覆盖影响力图、BT/FSM/GOAP/HTN、编队AI、势场、多层架构、LLM混合
- 核心发现：成功 RTS AI 都是 Strategy→Tactics→Micro 三层混合架构，没有单一形式化方法获胜
- 发现 roadmap 结构性盲区：专家系统缺乏明确的层级关系
- 产出 architecture_v2.md：
  - 三层执行架构（Strategy→Tactics→Micro）
  - Tactical Method 概念（有阶段状态的战术执行单元，解决"包围"问题）
  - 4层影响力图系统（terrain/vision/threat/support）
  - 8个战术方法模板
  - 完整系统全景图和开发优先级

## [2026-03-29 07:55] DONE — 补全遗漏需求 + 完善 plan
- 用户指出 plan 维护不够、遗漏看板设计等多个需求
- 重写 plan.md：5 大块 18 项任务（代码整理/看板设计/架构细化/需求记录/技术选型）
- 产出 user_requirements.md：6 大类需求 + 7 项已更正的过时假设 + 6 个开放问题
- 分配 yu 两个新任务：web-console 审计 + 全代码资产盘点 (msg_86307)
- 更正过时假设：增量兼容→全面重写，tick-driven→被动仲裁，IntelService保留→可重写

## [2026-03-29 08:00] DONE — 看板审计 + 代码资产盘点
- yu 完成 dashboard_audit.md: 现有控制台是厨房水槽，需要三区分离(Ops/Tasks/Diag)
  - 发现硬 bug: 前端 8090 vs 后端 8092 端口不一致
  - 看板需要后端先支持 task_snapshot/task_event 一等公民对象
- yu 完成 code_asset_inventory.md: 全量文件盘点
  - Keep: GameAPI、models、NLU 管线
  - Reference: jobs、agents、intel 双栈、tactical_core
  - Delete: 6+ standalone launchers/demos
  - 最高优先级重写: main.py (1327 行单体)
- 用户补充确认: 看板双模式(用户+调试) + 结构化日志系统

## [2026-03-29 08:15] DONE — 文档整合收敛
用户反馈：文档太多太散，要收敛成真正有用的文档。
- 7 份调查/调研文档归档至 archive/
- 所有架构决策、对象模型、接口约定收敛进唯一主文档 design.md
- 活跃文档从 12 → 6 个
- 新增用户决策：对手AI不纳入（另一个副官实例）、Task类型沿用roadmap、GameAPI不改
- Constraint 定位为"活跃修饰器"（不绑资源、无阶段、影响其他Task的执行策略）

## [2026-03-29 08:40] DONE — design.md 大幅重写，场景驱动
用户反馈：design.md "伪人感重"，堆砌关键词没有思考实际执行流。
核心问题：
  - Directive.target 不能是已解析实体（Interpreter 不查游戏状态）
  - Interpreter → Kernel 之间缺少 Resolver + Decomposer
  - 三层不是每个 Task 必经管线，是 Expert 内部可选工具
重写内容：
  - §1 改为"命令处理流水线"，逐步标注每步的输入/输出/实现/是否LLM
  - §2 对象模型增加 ResolvedTarget，Directive.target 改为未解析文本
  - §3 Kernel 简化为事件触发列表
  - §4 Expert 系统：明确"不是每个 Expert 都走三层"
  - §6 新增完整场景模拟："探索地图，找到敌人基地"全流程 + 时间线
  - §8 看板技术栈选定 Vue 3
  - 删除独立的"三层执行架构"章节，融入 Expert 系统描述

## [2026-03-30 00:20] DONE — design.md 全面重写 (Round 2)
用户指示：采纳 yu 的所有审查意见，修到能推演为止。
yu 审查发现 7 个 blocker（归档 archive/design_review.md）。
全部处理：
  1. 运行时矛盾→单线程 GameLoop 10Hz + per-expert tick_interval
  2. Action 路径→定义 Action/ActionResult/ActionExecutor（含 execute_batch 逻辑）
  3. 资源请求→ResourceRequest（predicates/mandatory/allow_wait/allow_preempt）
  4. 条件→SuccessCondition/FailureCondition 带 check() 方法
  5. 事件→Event dataclass + 检测算法（快照 diff）
  6. 取消/抢占→cancel_by_directive + 优先级抢占 + Expert.abort() 合约
  7. Schema→TaskSpec.blocked_by, ExecutionJob 扩展, Outcome 扩展, Constraint 扩展
  新增：NormalizedActor, Expert 生命周期, 启动顺序, WorldModel 分层刷新, ActionExecutor 去重
  新增场景边缘情况：侦察兵死亡→补充/失败, 取消命令流程, 资源抢占流程
  交给 yu 做 Round 2 审计 (msg_86417)

## [2026-03-30 00:50] DONE — design.md Round 3 修复
yu R2 审计发现 6 个剩余 gap（原 7 blocker 已关闭）。
全部修复：
  1. Outcome.result/JobStatus 对齐 → 统一用 "succeeded"，新增 PARTIAL
  2. 场景全字段补全 → ResourceRequest/Action/Outcome 所有字段填入具体值
  3. mid-task 资源 → Expert.start() 接收 resource_callback，ResourceRequest.wait_timeout_s
  4. Cancel → 新增 CancelSelector(directive_id/intent_match/job_id)，Kernel.cancel(selector)
  5. Dashboard 入站 → command_submit/cancel/clarification/mode_switch 四个 WS 事件
  6. Action resource_key → 替代 actor_id，支持 "actor:57"/"queue:Infantry"/"global"
交给 yu Round 3 审计 (msg_86419)

## [2026-03-30 01:35] DONE — design.md 审计收敛：Zero Blockers
5 轮迭代审计完成：
  R1: 7 blocker (架构矛盾) → 全关
  R2: 6 blocker (合约缺失) → 全关
  R3: 4 blocker (局部 gap) → 全关
  R4: 2 blocker (接口不一致) → 全关
  R5: 0 blocker ✅
design.md 可作为实现基础。

## [2026-03-30 02:00] DONE — 架构大转向：LLM agent + 大脑小脑模型
用户反馈推动三次架构转变：
  1. 合并 Interpreter/Resolver/Decomposer → CommandProcessor（后被 Adjutant 取代）
  2. 每个 Task = LLM agent 实例（大脑）+ Expert/Job 自主执行（小脑）
  3. 三级架构：Kernel(无LLM) / Task Agent(LLM) / Job(传统AI)
关键设计：
  - Job 直接调 GameAPI，无 ActionExecutor 中间层
  - 声明式资源模型（死了补、降级、不轻易 fail）
  - Expert 是写死的代码模块，Job config 是 per-Expert 强 schema
  - 大脑小脑协作：ExpertSignal + context packet 注入 + default_if_timeout
  - Task Agent 框架：raw SDK 自建 ~200 行
精简数据模型：14+ → 7 个

## [2026-03-30 03:00] DONE — 场景审计 7 轮全部通过 (A-I)
11 个测试场景全部 zero blockers（T1-T11）
拆出独立 test_scenarios.md，每步详细系统状态

## [2026-03-30 03:30] DONE — Adjutant 玩家交互层
设计 + 2 轮审计 zero blockers
TaskMessage/PlayerResponse schema、pending question timeout（Kernel 持有）、多问题路由规则

## [2026-03-30 04:00] DONE — 实现任务列表
implementation_plan.md：35+ 任务，7 Phase，4 里程碑
yu 审计后补充：WS 后端、timestamp 传播、review_interval 调度、Adjutant 路由测试

## [2026-03-30 04:15] DONE — the-seed 子库移除评估
用户决定移除 the-seed 框架子库（隔离增加复杂度，重写后不需要）
保留 OpenCodeAlert 游戏子库
yu 正在审计 the-seed 里是否有需要迁移的内容

## [2026-03-30 11:27] DONE — Phase 0 yu 侧全部完成
yu 完成全部 3 个任务：
- 0.5 benchmark (a325814) — xi 审计 PASS ✅
- 0.1 cleanup (6735e1e) — xi 审计 PASS ✅
- 0.1b the-seed removal (a4e7805) — xi 审计 PASS ✅
  迁移 NLU 规则到 nlu_pipeline/rules/，创建本地兼容包替代子库，.gitmodules 仅留 OpenCodeAlert
注意：benchmark commit 中混入了其他已 staged 文件（共享 index），未 rewrite history

## [2026-03-30 11:34] DONE — Phase 0 关闭 ✅
yu 交叉审计 xi 的 0.2/0.3/0.4：发现 2 blocker + 1 should-fix
- Blocker 1: Job.config 无 expert_type 绑定 → xi 加 EXPERT_CONFIG_REGISTRY + validate_job_config()
- Blocker 2: AnthropicProvider 多轮 tool-use 不完整 → 延后 Phase 1，加注释说明
- Should-fix: configs 用 enum 替换裸 str → xi 修复
xi 修复 commit 1f5a7ce → yu 回归审计 zero blockers (commit 461a83a)
wang 概念漂移检查通过

**Phase 0 全部 6 个任务完成，交叉审计通过：**
- 0.1 cleanup (yu/xi) ✅
- 0.1b the-seed removal (yu/xi) ✅
- 0.2 data models (xi/yu) ✅
- 0.3 directory structure (xi/yu) ✅
- 0.4 LLM abstraction (xi/yu) ✅
- 0.5 benchmark (yu/xi) ✅

## [2026-03-30 15:27] DONE — Phase 1 Batch 1 启动
分配：yu: 1.1 WorldModel / xi: 1.4 Task Agent，并行无文件冲突。

## [2026-03-31 00:00] DONE — Task 1.4 审计通过
xi 完成 Task Agent (d321a3e)，yu 审计发现 2 blocker（events 丢失 + defaults 空操作）+ 1 should-fix。
xi 修复 (ccbf442)，yu 回归审计 zero blockers。13 tests pass。
yu 的 1.1 WorldModel 仍在开发中。

## [2026-03-31 23:00] DONE — Phase 0-7 全部完成 + Live E2E Rounds 1-4
- Phase 1-7 全部开发完成（详见 live_test_log.md）
- 4 轮 Live E2E 测试，发现并修复 15+ 真实问题
- Round 4 结果：T5 ✅ / T9 ✅ / T1 ✅ / T2 ✅ / T7 ⚠️ / 0 ERROR ✅
- 关键修复：BASE_UNDER_ATTACK 误触发、LLM Expert 参数、actor category、建筑分配、GameAPI 长连接
- 用户反馈："行为正确但交互不正确，没有收到任何提示" → 分配 yu 修复

## [2026-04-01 06:10] DONE — Yu 修复 command feedback + defend_base reflex
- commit 2660436: RuntimeBridge._emit_adjutant_response() — 命令响应走 query_response 通道（聊天可见）
- commit 398902b: Kernel defend_base 即时反射 — BASE_UNDER_ATTACK 直接创建 CombatJob(HOLD)，不等 LLM
- 全量测试通过：14 kernel + 7 world_model + 10 adjutant + 7 ws + 6 game_control + E2E T1-T11
- 准备 Round 5 live E2E 验证

## [2026-04-01 06:30] DONE — Round 5 部分测试 + 系统深度分析
- T5 部署基地车 ✅ — MCV→建造厂成功
- T9 查询战况 ✅ — 副官返回完整中文简报（经济/军事/地图/建议）
- 命令反馈 ✅ — query_response 通道回显正常
- 发现 Issue 8（P0）：LLM 用 "PowerPlant" 但游戏要 "powr" → 所有建造失败
- 发现 Issue 9：production queue 查询返回 COMMAND_EXECUTION_ERROR
- 发现 Issue 10：WS world_snapshot 可能超 1MB 帧限制
- 发现 Issue 11：后端重启后 GameAPI 持久连接失效
- 产出 `docs/wang/system_analysis_v1.md`：完整架构 gap 分析 + 改进 roadmap
- 派 Yu 接手 live 测试 + 修复 Issue 8/9 + 前端修复

## [2026-04-01 07:00] DONE — 系统漂移分析 + 全链路调试方案
- 对照 design.md 逐项验证实现，产出 drift map（11 项完全实现、3 项有意简化、3 项 gap、5 项偏移）
- 关键发现：UnitRegistry 缺失是 Issue 8 根因，不是单纯的名称 bug
- 从 OpenCodeAlert yaml 提取完整单位注册表（建筑/车辆/步兵，含阵营/前置/成本）
- 产出 `docs/wang/system_drift_and_test_guide.md`：
  - Part 1: 设计 vs 实现漂移地图
  - Part 2: 当前阻断点
  - Part 3: 测试矩阵（在测什么、测什么没测）
  - Part 4: 全链路调试方案（4 层观测点、诊断决策树、日志关键词）
  - Part 5: 系统成熟度评估
- Yu 修复 Issue 8/9 + 建筑 queue 堵塞（3 commits），已派 Round 6 全链路测试
- 设 10min CronCreate 提醒监督 Yu 进展

## [2026-04-01 07:45] DONE — Yu Round 6 修复 8 个 live bug
Yu 在 Round 6 live 测试中发现建筑/经济链路有一叠 7 个相互关联的 bug：
1. dff8cb4: 终止 Task 后资源泄漏（queue:Building 不释放）
2. 21b15e5+65dde1c: auto-place 假成功（游戏侧+Python 侧双修）
3. 7af8a42: 简单建造命令 prompt 映射不足，改为 bootstrap 直接映射
4. a4f08fc: bootstrap 建造成功后 TaskAgent 重入 LLM 漂移到侦察
5. 777e8f0: EconomyJob 在建筑放置前就标记完成
6. e7daa12: 已有就绪建筑不计入完成数
7. 8b84985: blocked 状态不通知用户（低电力等）
8. 72d24cd: MCV 部署误触发 BASE_UNDER_ATTACK

验证结果：建造兵营全链路修复（不再漂移/卡队列），低电力正确显示警告。
尚未完成：需要干净游戏开始才能测试完整开局→侦察→战斗链

## [2026-04-01 08:51] DONE — Yu Round 6 最终报告 + Live Hardening 建议
Yu 交付 `docs/wang/live_round6_final_report.md`，核心结论：
- 底层运行时已稳定，主要问题从"会不会坏"转到"workflow 是否合理"
- 开局链全部验证通过：部署 ✅ 兵营 ✅ 矿场 ✅ 步兵 ✅ 侦察 ✅
- 本轮共修 12 个 live bug（建造链 8 个 + 反馈链 2 个 + runtime 2 个）
- 最大未闭环问题："攻击敌人"无目标时 LLM 过度动作（造车/扩产/漂移）
- 识别 5 项设计漂移需要正式记录
- 建议插入 Live Hardening 短周期再继续扩功能

## [2026-04-01 10:02] DONE — Live Hardening 前 5 项完成
按 queue 自动推进，Yu 连续完成：
1. ✅ ProductionAdvisor (79277e1) — query_planner 不再是 stub
2. ✅ Adjutant 规则路由 (d45688e) — 简单命令 0 LLM 延迟
3. ✅ 前端 WS 鲁棒性 (e5f4a9d) — 大帧限制+重连清理+状态指示
4. ✅ 系统可观测性 (ce400f8) — LLM reasoning 可见+组件过滤+benchmark 限流
5. ✅ UnitRegistry (7594501) — 从 yaml 加载，补齐 design.md 启动链
6. ✅ Live 测试自动化 (6499ac5) — test_live_e2e.py runner with phase-based CLI

## [2026-04-01 12:25] DONE — Round 7 全链验证 + Recon 收口修复
Round 7 结果（Hardening 后首次干净开局验证）：
- 建造兵营 ✅ succeeded，兵营 1→2
- 生产3个步兵 ✅ succeeded，步兵 0→3
- 探索地图 ✅ 功能正确（单位移动），但 40s 内未终态 → 已修收口条件
- 战况如何 ✅ 完整中文简报
- 矿场建造 ✅（earlier confirmed）
- 部署无 MCV ✅ 即时提示

Round 7 期间修复：
- 3c9787d: game reset 检测（外部重启游戏后自动清理旧 runtime）
- 4e94f81: deploy 无 MCV 快速返回
- 5455fc8: rule-routed task monitor-only（不再 LLM 漂移）
- 946e7e7: Recon 收口条件（超时→partial + waypoint 保持）
- 多个 UI 改进（可读任务编号、task trace、全局清空）

## [2026-04-02] DONE — NLU 完整接入 (由用户直接指挥 Yu)
- 1d64301: 旧 NLU 前半段接入 Adjutant（shorthand + 复合序列）
- 0925062: 完整 NLU runtime 集成（deploy_mcv/produce/explore/mine/stop_attack/query_actor）
- 不使用旧 SimpleExecutor，执行层全部走当前 Adjutant/Kernel/Expert 链
- 24 adjutant + 10 routing + 8 game_control + 9 ws 测试通过

## [2026-04-04 00:00] DONE — 文档结构深度整理
- docs/wang/: 40+ 文件 → 15 个活跃文件，其余归档到 archive/
- 移入 archive: 23 个 xi_* 审计文件、7 个已完成调查文件、4 个 benchmark 数据文件、1 个重复 feedback 文件
- 根目录: FIXES_SUMMARY.md + FIX_LLM_STATS.md → docs/archive/（过时的 2026-01 修复记录）
- 保留 15 个活跃文档：design.md、dev_progress.md、implementation_plan.md、research docs、system analysis 等

## [2026-04-04 00:30] DONE — 开发进度深度整理
- 分析最近 100 个 git commit (2026-03-20 ~ 2026-04-04)
- dev_progress.md 补充 Phase 2-9 完整进度（之前只有 Phase 0-1）
- 100 commits = 50 fix + 20 feat + 19 docs + 7 chore + 3 test + 1 refactor
- 覆盖：Xi Live集成 → 基础设施硬化 → Live测试Rounds 3-7 → 架构Hardening → Expert知识集成 → NLU完整接入
