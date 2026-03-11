# Audit of xi `1.5 Task tools + 1.7 timestamp` (`ddd5004`)

## Scope
- `task_agent/handlers.py`
- `tests/test_tool_handlers.py`

## Verification
- Ran `python3 tests/test_tool_handlers.py` and confirmed all `8` tests pass.
- Ran a live integration repro with the current `Kernel` + `WorldModel` + `TaskToolHandlers` to verify real side effects for constraint tools.

## Findings

### 1. Blocker — `create_constraint` / `remove_constraint` claim success but do not mutate runtime state
- File: `task_agent/handlers.py:111-128`
- `handle_create_constraint()` constructs a `Constraint`, then immediately returns a generated `constraint_id` with a TODO comment instead of calling a Kernel method.
- `handle_remove_constraint()` always returns `{"ok": True, ...}` and does not remove anything.
- This is not just an incomplete future hook. The live Kernel already has real implementations for this contract in `kernel/core.py:846-865`, and `WorldModel` already exposes `set_constraint()` / `remove_constraint()` in `world_model/core.py:407-410`.
- Live repro result:
  - `create_constraint` returned a `constraint_id`
  - `world.query("constraints")` remained empty after create
  - `remove_constraint` returned `ok=True`
  - `world.query("constraints")` still remained empty after remove
- Impact: a Task Agent can believe a constraint has been installed or cleared while the actual runtime state is unchanged. That breaks the `1.5` tool contract and makes the `1.7` timestamped success response misleading.

### 2. Should-fix — tests only verify timestamps for constraint tools, not behavior
- File: `tests/test_tool_handlers.py:222-249`
- The current suite checks that `create_constraint` and `remove_constraint` responses include `timestamp`, but it never asserts that a constraint is actually stored or removed.
- The same root cause is visible in `task_agent/handlers.py:23-32`: `KernelLike` does not even declare `create_constraint` / `remove_constraint`, so a stubbed handler can pass type checks and the current test doubles without pressure to match the live Kernel surface.
- Recommended fix:
  - extend `KernelLike` with constraint methods
  - add a real side-effect test that verifies create populates runtime/world state and remove clears it

## Passes Confirmed
- `register_all()` wires all 11 tools.
- `start_job()` uses `EXPERT_CONFIG_REGISTRY` to build config objects.
- `query_world()` maps supported query types into `WorldModel.query()`.
- All handler responses include `timestamp`, including the new `1.7` requirement.

## Conclusion
Not `zero-gap`. I see `1 blocker + 1 should-fix`.
