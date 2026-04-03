# Audit: xi `2.1 Expert Base` + `1.2 GameLoop`

## Findings

### 1. `experts/base.py` abort path can self-corrupt `ABORTED` back to `WAITING`
- File: `experts/base.py`
- Lines: `158-166`, `177-184`
- Severity: blocker

`BaseJob.abort()` sets `status = ABORTED`, but `on_resource_revoked()` later unconditionally sets `status = WAITING` when the last resource is removed. In the real lifecycle, Kernel abort often implies resource release right after abort. That means an aborted Job can end up reporting `waiting` instead of `aborted`.

Minimal repro I ran locally:

```python
job.on_resource_granted(["actor:1"])
job.abort()
job.on_resource_revoked(["actor:1"])
print(job.status.value)  # waiting
```

This is a real state-machine bug, not just a test gap.

### 2. `GameLoop` interface does not match the current Kernel surface
- File: `game_loop/loop.py`
- Lines: `33-36`, `160-162`
- Severity: blocker

`GameLoop` requires `kernel.route_events(events: list[Event])`, but the current Kernel task-lifecycle surface is `route_event(event: Event)` skeleton only. This is not just naming drift in docs; with the current codebase, `GameLoop` cannot route real events into Kernel once events exist.

Minimal repro I ran locally against the current `Kernel` + `WorldModel`:

```python
world.refresh(now=100.0, force=True)
source.set_frame(1)  # produce real events
asyncio.run(loop._tick())
```

Result:

```text
AttributeError: 'Kernel' object has no attribute 'route_events'
```

So `1.2` is not integration-ready against the current `1.1/1.3a` surface.

### 3. `GameLoop` double-routes events with the current `WorldModel.refresh()` contract
- File: `game_loop/loop.py`
- Lines: `154-158`
- Severity: blocker

`GameLoop._tick()` takes events from `world_model.refresh(now=now)` and then immediately calls `world_model.detect_events(clear=True)` and concatenates both. But the current `WorldModel.refresh()` already returns the same newly detected `Event[]` that `detect_events()` exposes. So every event gets routed twice.

Minimal repro I ran locally against the current `WorldModel`:

```text
routed 14
['ENEMY_DISCOVERED', 'UNIT_DAMAGED', 'UNIT_DAMAGED', 'ENEMY_EXPANSION',
 'BASE_UNDER_ATTACK', 'PRODUCTION_COMPLETE', 'ECONOMY_SURPLUS',
 'ENEMY_DISCOVERED', 'UNIT_DAMAGED', 'UNIT_DAMAGED', 'ENEMY_EXPANSION',
 'BASE_UNDER_ATTACK', 'PRODUCTION_COMPLETE', 'ECONOMY_SURPLUS']
```

This is a contract mismatch between `1.1` and `1.2`. Either:
- `refresh()` should return `None`/not return events and `detect_events()` is the sole source, or
- `refresh()` returns events and `GameLoop` must not drain them again in the same tick.

## Non-blocking notes

### 4. `pause()/resume()` in `BaseJob` do not mechanically update `status`
- File: `experts/base.py`
- Lines: `148-156`
- Severity: should-fix

They only toggle `_paused`. That is enough for `do_tick()` to skip execution, but it leaves `to_model().status` stale as `running`, which is misleading for context packets, dashboards, and scheduling logic unless every caller remembers to patch `status` separately.

### 5. Tests miss the three failing integration/state-machine paths above
- Files: `tests/test_expert_base.py`, `tests/test_game_loop.py`
- Severity: should-fix

Current tests all pass, but they do not cover:
- abort + resource revoke sequence
- `GameLoop` against the real Kernel interface
- `GameLoop` against the real `WorldModel.refresh()` + `detect_events()` interaction

## What is good

- The three-ABC split in `experts/base.py` is conceptually aligned with `design.md`.
- `BaseJob.do_tick()` is small and mechanically clear.
- `GameLoop`’s intended tick order matches `design.md §2`.
- Existing tests are readable and fast, so adding the missing regression cases should be cheap.

## Verdict

Not `zero-gap`.

- `2.1 Expert Base`: 1 blocker + 1 should-fix
- `1.2 GameLoop`: 2 blockers + 1 should-fix/test gap

Both tasks need follow-up before they can be treated as integration-ready.
