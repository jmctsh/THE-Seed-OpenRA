# Regression Audit of xi Batch 4 fix (`8e594c4`)

## Scope
- `game_loop/loop.py`
- `task_agent/queue.py`
- `tests/test_ws_and_review.py`
- `tests/test_game_loop.py`

## Verification
- Ran `python3 tests/test_ws_and_review.py` and confirmed all `7` tests pass.
- Ran `python3 tests/test_game_loop.py` and confirmed all `7` tests pass.
- Ran `python3 -m py_compile game_loop/loop.py task_agent/queue.py tests/test_ws_and_review.py tests/test_game_loop.py`.
- Re-ran two live repros:
  - real `Kernel + GameLoop` pending-question timeout flow
  - direct `AgentQueue.trigger_review()` then `wait_for_wake()` edge case

## Findings

### Cleared — `GameLoop` now drives Kernel-side timeout logic
- File: `game_loop/loop.py:34-39`, `game_loop/loop.py:192-199`
- `KernelInterface` now declares `tick(now=...)`.
- `GameLoop._tick()` now calls `self.kernel.tick(now=now)` once per loop iteration.
- Live repro result:
  - register a real `task_question` with `timeout_s=0.05`
  - run the real `GameLoop` for ~120ms
  - the question expires, `pending_questions` becomes empty, and the Task Agent receives default `PlayerResponse(answer="no")`
- This closes the previous blocker where Batch 4 timeout logic was unreachable from the live main loop.

### Remaining Blocker — `trigger_review()` still loses a pre-wait review wake
- File: `task_agent/queue.py:46-70`
- The new sentinel approach is an improvement over poking `_wake_event` directly, but it is not yet actually race-free in the claimed sense.
- `wait_for_wake()` still starts by clearing `_wake_event`.
- If `trigger_review()` happens just before the agent enters `wait_for_wake()`, the event bit is cleared, and the queued sentinel does not wake the waiter by itself.
- Minimal repro on the live queue:
  - call `trigger_review()`
  - immediately call `await wait_for_wake(timeout=0.05)`
  - result: `False`
  - `drain()` then returns `[]` because the sentinel gets filtered out
- Impact: a due review can still be delayed until the full timeout path instead of waking promptly. This is better than the previous version in terms of intent, but it does not fully satisfy the “race-free review wake” claim.

## Conclusion
Not `zero blockers`. I clear the previous `Kernel.tick()` blocker, but I still see `1 blocker` remaining on the `review_interval` wake semantics.
