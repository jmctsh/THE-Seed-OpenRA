# Live Round 6 Final Report

Date: 2026-04-01
Author: yu

## 1. Executive Summary

这轮 live 测试暴露出的问题，不是单个 bug，而是三类问题叠加：

1. **生产/建造 workflow 的确定性不够**
   - 典型表现：建筑卡队列、任务已成功但建筑没真正落地、简单命令被 LLM 漂移成别的任务。
   - 这一类现在已经基本修到可用。

2. **用户反馈语义不清**
   - 典型表现：命令执行了但聊天区没回执，内部等待态被错误显示成玩家告警。
   - 这一类也已经修到基本可用。

3. **设计与 live reality 之间存在系统性漂移**
   - 典型表现：设计假设单线程主循环足够，但 live 里同步 GameAPI 轮询会饿死 asyncio；设计假设 Task Agent 可以通过通用 LLM tool-use稳定完成所有简单命令，但 live 里必须给常见命令加 deterministic bootstrap；设计里 `BASE_UNDER_ATTACK` 是“自动建 Task”，但 live 里这个延迟对即时防御不可接受。

结论：

- **当前系统已经不再处于“看起来通、live 一碰就碎”的状态。**
- **开局建造链的主要硬问题已经关闭。**
- **但“攻击敌人（无可见目标）”这类开放式命令仍然暴露出一个未收口的高层 workflow 问题。**
- 现在最合理的下一步不是继续扩 feature，而是做一个短周期的 **live hardening**：先把当前 workflow 收紧，再恢复大规模功能推进。

## 2. 本轮已确认并修复的问题

### 2.1 生产/建造链

这条链路是本轮问题最密集的区域，已确认并修复的根因包括：

- **终态 Task/Job 资源未释放**
  - 结果：后续建造任务拿到错误的队列状态。

- **auto place 语义不可靠**
  - 游戏侧可能返回“成功”，但 ready building 实际没有被放下。
  - Python 侧此前只信返回值，不核验队列变化。

- **简单建造命令只靠 prompt 引导，不够稳定**
  - `建造矿场` / `建造兵营` 这类命令会被 LLM 漂移成侦察或其他行为。

- **bootstrap 成功后重新回到 LLM，导致任务漂移**
  - 典型现象：兵营已经正确走到 `EconomyExpert`，随后 TaskAgent 又二次进入 LLM，把任务带偏。

- **Building 队列的完成语义错误**
  - `PRODUCTION_COMPLETE` 不等于“任务真的完成”，因为 ready building 可能还没落地。

- **队列里预先存在的 ready building 不计入当前任务完成**
  - 这会导致“队列被清空了，actor 也增加了，但任务还挂着”。

- **简单生产命令的名称映射不稳**
  - live 中 `步兵` 这种高频命令不能继续依赖 LLM 自由选名字，必须 deterministic 地落到 ruleset-backed id。

- **`queue_unassigned` 被错误当成玩家 blocker**
  - 它本质上只是资源尚未分配的内部等待态，不该打成用户告警。

这条链现在的状态是：

- `部署基地车`
- `建造兵营`
- `建造矿场`
- `生产3个步兵`

都已经在 live/current-state 路径上确认跑通过，且“步兵新增”已确认不是旧单位重复计数。

### 2.2 用户反馈链

本轮修掉了两个关键问题：

- **命令/回复反馈走错通道**
  - 之前 `command/reply` 被塞进 `player_notification`，聊天主通道没有副官回执，用户体感像“系统没反应”。
  - 现在同步回执统一走聊天主通道 `query_response`。

- **前端会把内部等待态/旧消息继续展示出来**
  - Chat 历史已从 `localStorage` 改成 `sessionStorage`。
  - 但当前 session 内的旧 notification 仍然会继续存在，直到刷新/重开 session。
  - 这意味着：“如果现在还看见 `生产队列资源未分配，等待中`，大概率是旧消息残留，不是新 warning 仍在产生。”

### 2.3 Runtime / 基础设施

本轮已确认并修复的 runtime 级问题：

- **GameLoop 同步阻塞 I/O 饿死 asyncio**
  - 已将 `WorldModel.refresh()` 和 `job.do_tick()` 移到 worker thread。

- **GameAPI 每请求新建 socket，导致 log spam 且效率差**
  - 已改成长连接复用 + 明确消息 framing。

- **OpenCodeAlert 连接级日志刷屏**
  - 已降到 debug。

- **`BASE_UNDER_ATTACK` 误触发**
  - 现在不再把所有建筑掉血都升级成基地受攻击。

- **`BASE_UNDER_ATTACK` 响应过慢**
  - 现在 Kernel 直接起即时防御 `CombatJob`，不再先建 task 再等 LLM。

- **WorldModel actor category 误判**
  - 中文建筑名不再默认掉到 `vehicle`。

- **软资源匹配会把建筑分给 ReconJob**
  - 现在默认排除 `building/static`，除非 ResourceNeed 明确要求。

## 3. 仍未真正收口的问题

### 3.1 `攻击敌人` 在无可见目标时的 workflow 仍然不对

这是目前最重要的未闭环问题。

live 里当前表现不是“完全不动”，而是**错误地过度动作**：

- 没有先给用户一个快速、明确的解释
- 没有稳定地走“先侦察，再攻击”的窄路径
- 反而会尝试：
  - `query_planner(ProductionAdvisor)`
  - 造 `jeep`
  - 进一步扩生产/补电
  - 起多个 Movement/Combat job
- 最后过了很长时间才以 `partial` 收尾

这在 workflow 层是错误的，因为：

- 它不符合用户对“攻击敌人”的直接预期
- 它把“当前无目标”升级成了大规模自主战略扩展
- 它没有及时告知玩家为什么现在不能直接攻击

根因组合：

1. `TaskAgent` prompt 没有把“无可见目标”约束成明确分支
   - 正确分支应该只有两种：
     - 明确回复：未发现敌人，需要先侦察
     - 或者：显式转成受控的 Recon path

2. `query_planner` tool 还暴露着，但实现是 stub
   - `task_agent/handlers.py` 里 `query_planner` 仍返回 `status=unimplemented`
   - 这会让 LLM 把“空规划器”当成可用能力，继续往错误方向推演

3. 当前 TaskAgent 对“开放式战斗命令”的自由度过大
   - 简单 build/produce 命令已经证明：某些高频路径不能只靠 prompt 自由发挥
   - `攻击敌人（无目标）` 很可能也属于需要“收窄选择空间”的命令类型

### 3.2 Live test methodology 仍然不是一等公民

当前 repo 里有大量 mock E2E / scenario tests，这些测试是有价值的，但本轮已经反复证明：

- **它们更适合回归，不适合发现 live workflow 问题**

本轮真实暴露的大多数问题，都是以下类型：

- 游戏侧真实 queue 语义
- auto place 实际效果
- socket/loop 交互
- runtime 集成时序
- 前端消息生命周期

这些都不是旧 mock E2E 能稳定提前暴露出来的。

现在缺的是一套正式的 live test 规程/工具，而不是更多 mock case。

### 3.3 前端消息生命周期仍然有“旧消息残留”的认知成本

虽然聊天历史已经降到 `sessionStorage`，但对 live 调试来说仍有一个 UX 问题：

- 旧 `player_notification` 会在当前 session 持续存在
- 用户很容易把“旧告警”误认成“当前系统刚发的新告警”

这不是架构 blocker，但对 live 调试很伤，尤其在需要快速判断“修复是否生效”时。

## 4. 当前实现与冻结设计的主要漂移

`docs/wang/design.md` / `implementation_plan.md` 已冻结，所以这里不是建议直接改设计，而是给 Wang 和用户讨论时用的“漂移清单”。

### 漂移 1：单线程 GameLoop 已不成立

设计写的是：

- **单线程 GameLoop，默认 10Hz**

但 live 现实证明：

- `WorldModel.refresh()` 和 job tick 中存在同步 GameAPI I/O
- 如果仍严格把它们留在 asyncio 主循环线程内，Adjutant/LLM 会被饿死

当前实际实现已经变成：

- 主 asyncio loop 跑 WS / Adjutant / TaskAgent LLM
- 阻塞游戏 I/O 下沉到 worker thread

这不是小实现细节，而是运行时模型漂移。

### 漂移 2：Task Agent “通用 tool-use” 不足以覆盖高频简单命令

设计默认是：

- Task Agent 理解意图
- 通过 tool_use 选择 Expert / 配参数

但 live 现实是：

- `建造矿场`
- `建造兵营`
- `生产3个步兵`

这类高频简单命令若完全交给 LLM 自由解释，稳定性不够。

当前系统已经实际引入：

- deterministic bootstrap for simple structure build
- deterministic bootstrap for simple infantry production

所以设计实际上已经漂向：

- **“开放式复杂任务走 LLM；高频窄域命令走 deterministic bootstrap + LLM 协调收口”**

这点建议被明确记录，否则后续会反复在“是不是应该全靠 LLM”上摆动。

### 漂移 3：`BASE_UNDER_ATTACK` 已从“auto Task”漂到“即时 Job 反射”

设计原文更偏向：

- `BASE_UNDER_ATTACK -> auto create Task("defend_base")`

但 live 里这条路径太慢。

当前实际实现已经是：

- Kernel 直接起/重定向即时防御 `CombatJob`
- task/LLM 只处理后续协调

这说明对某些强实时被动事件，设计已经从“Task-first”漂到“Job-first reflex”。

### 漂移 4：Planner 在设计上存在，但 runtime 中还不该暴露

设计允许：

- `query_planner`
- Planner Expert（ReconRoutePlanner / AttackRoutePlanner / ProductionAdvisor）

但当前 runtime reality 是：

- Planner 仍未实现
- tool surface 仍把它暴露给 TaskAgent
- 这会直接制造错误行为

这不是“缺功能”，而是“接口暴露早于能力落地”。

### 漂移 5：用户反馈语义在设计里不够明确

设计里有：

- `player_notification`
- `task_info / task_warning / task_complete_report`
- Adjutant 输出

但本轮 live 证明还缺一层明确语义：

- 什么是同步回执
- 什么是异步通知
- 什么是内部等待
- 什么才算玩家 blocker

没有这层规则，系统会不断把“内部状态”误报给用户。

## 5. 我对当前系统状态的判断

### 5.1 已经稳定下来的部分

- GameAPI 连接层
- GameLoop 不再饿死 Adjutant/LLM
- WorldModel 基本查询与事件基础
- Kernel 资源分配/抢占的主要误分配问题
- 生产/建造链的大部分真实队列问题
- 用户命令回执主通道
- 基地受攻击的即时反射防御

### 5.2 仍然脆弱的部分

- 开放式战斗命令的高层策略边界
- Planner/LLM/tool surface 的一致性
- live testing 工具链
- 前端对“旧消息 vs 新消息”的区分

## 6. 建议的下一阶段计划

我建议下一阶段不要立刻继续扩功能，而是插入一个短周期 **Live Hardening**。

### P0：先收口当前最真实的 live 问题

1. **修 `攻击敌人` 无目标 workflow**
   - 目标：不再长时间漂移到造车/扩生产
   - 正确行为：
     - 要么立即回复“未发现敌人，需要先侦察”
     - 要么受控地转为 Recon path
   - 不允许继续 silent long-running strategic drift

2. **暂时移除或硬禁止未实现的 `query_planner` runtime 使用**
   - 在 Planner 真实现前，不应继续暴露给 TaskAgent 作为可用能力

3. **给 live 调试加“消息清零”能力**
   - 最小方案：restart/sync 时清理前端 session message history
   - 更好方案：把 notification 分成“当前有效”和“历史记录”

### P1：把 live test 提升为正式工程资产

1. 建一个正式的 live test runner / checklist
   - 发命令
   - 抓聊天回执
   - 抓 task/task_message/player_notification
   - 抓关键 GameAPI 状态快照
   - 记录 elapsed

2. 定义一组 canonical live scenarios
   - 开局建造链
   - 简单生产链
   - 侦察
   - 攻击（有目标 / 无目标）
   - 基地受攻击即时反应

3. 建一个“当前游戏状态可测 / 干净 baseline 可测”的双模式规程
   - 当前状态 live test 用来找 workflow 问题
   - baseline live test 用来做回归确认

### P2：把漂移正式沉淀为 dev decisions

如果用户认可，建议 Wang 记录到 `docs/wang/dev_decisions.md`：

1. GameLoop 的阻塞游戏 I/O 下沉到 worker thread
2. 高频简单命令允许 deterministic bootstrap，不强求全量 LLM 解释
3. `BASE_UNDER_ATTACK` 允许 Kernel 直接起即时防御 Job
4. 未实现 Planner 不应暴露在 live runtime tool surface
5. 玩家只应看到真正 blocker，不应看到内部等待态

## 7. Final Assessment

如果问“当前系统离可用还有多远”，我的判断是：

- **底层运行时已经基本站住了。**
- **最大的问题已经从“底层会不会坏”转成“高层 workflow 是否合理”。**

这是好事，因为它意味着：

- 现在不是在修地基塌方
- 而是在收紧系统行为边界

因此我建议：

- **暂停继续加新能力**
- **先做一轮 live hardening**
- **把这轮暴露出来的行为边界和设计漂移正式记账**

只要这一步做完，后续再继续扩 Expert / Planner / 交互层，成本会明显更低，且不会反复回到同样的 live workflow 问题上。
