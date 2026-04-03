# xi Phase 2-4 回归审计（505a044）

审计目标：验证上轮提出的 3 个 blocker + 1 个 should-fix 是否关闭。

结论：**不是 zero blockers。**  
这次修复**确实关闭了 2 个 blocker**：
- Expert 与真实 `GameAPI` 契约不一致
- `MovementJob` 把“全灭/查不到 actor”误判为成功到达

但还剩：
- **1 个 blocker**：`3.5` 的 `tests/test_e2e_experts.py` 仍不是实链 E2E
- **1 个 should-fix**：`NotificationManager` 的 retry 逻辑仍会跳过中间失败项

## 已关闭

### 1. GameAPI 契约漂移已修

涉及：
- `experts/game_api_protocol.py`
- `experts/movement.py`
- `experts/deploy.py`
- `experts/combat.py`

现在三类 Expert 都改成了与真实共享接口一致的调用方式：
- 移动：`move_units_by_location(List[Actor], Location, attack_move=...)`
- 部署：`deploy_units(List[Actor])`
- 攻击：`attack_target(Actor, Actor)`

我本地用 real-shape 假接口复验：
- `MovementJob.do_tick()` 现在会实际调用 `move_units_by_location([Actor(57)], Location(...), ...)`
- `CombatJob.do_tick()` 不再因缺少 `move_actors(...)` 直接抛 `AttributeError`

### 2. `MovementJob` 的“全灭=到达”误判已修

涉及：
- `experts/movement.py:118-132`

`_all_arrived()` 现在引入 `alive_count`，当所有 actor 都查不到时返回 `False`，不再错误完成任务。

我复验了最小复现：
- `actor:57` 资源仍在
- `world_model.query("actor_by_id", {"actor_id": 57}) -> {"actor": None}`
- `job.do_tick()` 后：
  - `status == running`
  - 没有 `task_complete(result="succeeded")`
  - 会继续发移动命令而不是误报完成

## Remaining findings

### 1. Blocker — `3.5` 的 `tests/test_e2e_experts.py` 仍然不是实链 E2E，commit `505a044` 并没有修这个问题

涉及：
- `tests/test_e2e_experts.py:1-7`
- `tests/test_e2e_experts.py:66-108`
- `tests/test_e2e_experts.py:142-161`

这次 commit 的实际 diff **没有修改** `tests/test_e2e_experts.py`，所以它的结构性问题还在：
- 没有真实 `Kernel`
- 没有真实 `WorldModel`
- 没有真实 `GameLoop`
- 没有资源分配 / 抢占
- 没有 Event 路由
- 没有 Job tick 调度

更关键的是：
- `MockKernel.start_job()` 仍保留 fallback 假实现（`tests/test_e2e_experts.py:77-87`）
- 大多数场景仍然是 `kernel = MockKernel()`，并没有注册真实 `MovementExpert` / `DeployExpert` / `CombatExpert` / `EconomyExpert`

所以这批测试依然主要是在验证：
- TaskAgent 有没有发出某个 tool call

而不是验证：
- T2-T8 的真实主链是否在共享运行时下可用

按里程碑口径，这个 blocker 没关。

### 2. Should-fix — `NotificationManager` 的 retry 仍然会跳过中间失败项，并重复推送后面的成功项

涉及：
- `adjutant/notifications.py:129-145`

这次修法是：
- 记录 `failed_count`
- 结束后做 `self._pushed_count = len(all_notifications) - failed_count`

这个逻辑只在“所有失败都发生在尾部”时才正确。  
如果失败发生在中间，会出现错位：

最小复现：
- Kernel 通知序列：`A, B, C`
- sink 第一次只在 `B` 上失败

实际结果：
- 第一次 `poll_and_push()` 后 `total_pushed == 2`
- 第二次 `poll_and_push()` 只会从索引 `2` 开始重试，也就是只重推 `C`
- `B` 被永久跳过
- `C` 被重复推送

我本地复现输出：
- first poll: `A, B, C`
- pushed_count after first: `2`
- second poll: only `C`
- sink calls: `['A', 'B', 'C', 'C']`

所以“失败项下次重试”这个语义还没有真正成立。

## 本地验证

我跑了：
- `python3 tests/test_movement_deploy.py`
- `python3 tests/test_combat.py`
- `python3 tests/test_e2e_experts.py`

另外做了两组 live repro：
- real-shape GameAPI 调用复验
- `NotificationManager` 中间失败重试复验

## 结论

这轮不能清成 `zero blockers`。

当前状态应当是：
- 已关闭：2 个 blocker
- 未关闭：1 个 blocker（`3.5` E2E 真实性）
- 未关闭：1 个 should-fix（通知重试语义）

