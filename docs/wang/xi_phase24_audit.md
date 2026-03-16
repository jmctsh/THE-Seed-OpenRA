# xi Phase 2-4 集中审计

审计范围：
- `4.1` Adjutant LLM
- `4.2+4.3` 查询 + 通知
- `4.4` Adjutant 路由测试
- `3.2` MovementExpert
- `3.4` DeployExpert
- `3.3` CombatExpert
- `3.5` E2E T2-T8

结论：**不是 zero-gap**。我确认 Adjutant 基础路由和现有单测总体方向是对的，但当前还有 **3 个 blocker**，其中 2 个在 Expert 运行时契约，1 个在里程碑测试有效性。

## Findings

### 1. Blocker — `MovementExpert` / `DeployExpert` / `CombatExpert` 使用了不存在于真实 `GameAPI` 的接口，live 集成会直接断

涉及：
- `experts/movement.py:21-28, 90-97`
- `experts/deploy.py:19-20, 59-63`
- `experts/combat.py:26-29, 146-150, 190-191, 224-229`
- 对照真实接口：
  - `openra_api/game_api.py:373-394` `move_units_by_location(self, actors: List[Actor], location: Location, attack_move=False)`
  - `openra_api/game_api.py:674-691` `deploy_units(self, actors: List[Actor])`
  - `openra_api/game_api.py:731-757` `attack_target(self, attacker: Actor, target: Actor)`

问题：
- `MovementJob` 假定有 `game_api.move_actors(actor_ids, position, attack_move=...)`
- `DeployJob` 假定有 `game_api.deploy_actor(actor_id)`
- `CombatJob` 假定有：
  - `game_api.move_actors(actor_ids, position, attack_move=...)`
  - `game_api.attack_target(actor_ids, target_actor_id)`

但真实 OpenRA `GameAPI` 暴露的是：
- 批量移动：`move_units_by_location(List[Actor], Location, attack_move=...)`
- 部署：`deploy_units(List[Actor])`
- 攻击：`attack_target(Actor, Actor)`，不是 `(list[int], int)`

这不是“命名不统一”的小问题，而是 **对象形状和调用约定都不一致**。我做了 3 个最小复现：
- `MovementJob` 注入一个只带真实方法名的 `RealishAPI(move_units_by_location)`：`do_tick()` 记录警告 `"object has no attribute move_actors"`，Job 保持 `running` 且没有任何行动副作用
- `DeployJob` 注入 `RealishAPI(deploy_units)`：首 tick 直接走异常分支并 `failed`
- `CombatJob` 注入 `RealishAPI(move_units_by_location, attack_target(attacker, target))`：首 tick 直接 `AttributeError: ... has no attribute move_actors`

也就是说，这三个 Expert 当前只能在自定义 mock API 上通过，接到共享 `openra_api.GameAPI` 就会失效。

### 2. Blocker — `MovementJob` 会把“所有单位都丢了/查不到”误判成“全部到达”，错误发出成功完成

涉及：
- `experts/movement.py:78-88`
- `experts/movement.py:118-129`

根因：
- `_all_arrived()` 对 `actor_by_id` 查不到的单位直接 `continue`
- 如果所有资源 actor 都已经死亡、丢失或者 WorldModel 查不到，那么循环会一路 `continue` 到结束，然后返回 `True`
- `tick()` 随后立即发 `task_complete(result="succeeded")`

最小复现：
- 资源里只有 `actor:57`
- `world_model.query("actor_by_id", {"actor_id": 57}) -> {"actor": None}`
- `job.do_tick()` 后：
  - `status == succeeded`
  - 发出 `Signal(task_complete, result="succeeded")`

这会把“撤退途中全灭”“维修路上单位丢失”“单位被回收/未同步”错误报告成成功完成，属于行为级错误，不是单纯状态细节。

### 3. Blocker — `3.5` 的 `tests/test_e2e_experts.py` 不是实链 E2E，当前测试可以在完全不跑 Expert 运行时的情况下通过

涉及：
- `tests/test_e2e_experts.py:1-7`
- `tests/test_e2e_experts.py:66-108`
- `tests/test_e2e_experts.py:142-161`
- 示例场景：
  - `tests/test_e2e_experts.py:169-178`
  - `tests/test_e2e_experts.py:194-207`
  - `tests/test_e2e_experts.py:223-235`
  - `tests/test_e2e_experts.py:250-260`

问题不是“mock 太多”，而是测试对象已经变成了另一个系统：
- 没有真实 `Kernel`
- 没有真实 `WorldModel`
- 没有 `GameLoop`
- 没有资源分配
- 没有 Event 路由
- 没有 Job tick 调度
- 没有 Task/Job 生命周期联动

更严重的是：
- `MockKernel.start_job()` 在 `experts` registry 里找不到 expert 时，会直接 fallback 返回一个假的 `JobModel`（`tests/test_e2e_experts.py:77-87`）
- 而大多数场景都是 `kernel = MockKernel()`，根本没有注册任何 `MovementExpert` / `DeployExpert` / `CombatExpert` / `EconomyExpert`
- 所以这些测试多数情况下只是验证“TaskAgent 能不能发出某个 tool call”，不是验证“系统能不能跑通 T2-T8”

换句话说，`3.5` 现在不能作为里程碑 2 的有效通过证据。它没有覆盖 Wang 设计里要求的主链：
- `Kernel.start_job(...)` 真创建运行时 Job
- `Kernel` 资源绑定 / 抢占
- `GameLoop` 驱动 tick
- Expert 真正调用 GameAPI
- Signal / Event 回流
- Task 最终完成

## Should-fix

### A. `NotificationManager` 在 sink 推送失败时仍然推进 `_pushed_count`，会永久丢通知

涉及：
- `adjutant/notifications.py:129-141`

现状：
- 某条通知如果 `await self._sink(...)` 抛异常，只会打日志
- 循环结束后仍然执行 `self._pushed_count = len(all_notifications)`

结果：
- 这条通知被视为“已经消费”
- 下次 `poll_and_push()` 不会再重试
- 短暂 WS 故障 / sink 异常会造成通知永久丢失

这条我没上升成 blocker，因为它不阻止代码运行，但它会破坏 `4.3` 的可靠性语义。

## 已验证项

我本地跑过：
- `python3 tests/test_adjutant.py`
- `python3 tests/test_adjutant_routing.py`
- `python3 tests/test_movement_deploy.py`
- `python3 tests/test_combat.py`
- `python3 tests/test_e2e_experts.py`

这些测试当前都能通过；问题在于：
- 一部分单测 mock 了错误的 API 契约，因此绿灯不代表能接 live runtime
- `3.5` 的“E2E”覆盖面不足以证明 Milestone 2 主链可用

## 建议修复顺序

1. 先统一 `Movement/Deploy/Combat` 和真实 `GameAPI` 的适配层
2. 修 `MovementJob` 的“actor 缺失 = 成功到达”误判
3. 重写 `tests/test_e2e_experts.py`，至少切到真实 `Kernel + WorldModel + GameLoop + Expert`

