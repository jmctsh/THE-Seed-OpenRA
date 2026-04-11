## Current
Testing reform / signal quality: keep tightening startup/runtime signal so backend health is measured by layered contracts (`unit`, `contract`, `startup_smoke`, `runtime_invariants`, `live`) instead of one broad green count, and close the next false-green surface exposed by direct runtime regressions.

## Queue
Testing reform / signal quality: add a real `startup_smoke` layer for `main.py -> run_runtime() -> ApplicationRuntime.start()` with `enable_ws=True`, fail fast on background asyncio task exceptions, and report test status by layer (`unit`, `contract`, `startup_smoke`, `runtime_invariants`, `live`) instead of a single large green count.
Runtime disconnect degradation: investigate and fix the post-game-close path where `world_model` loops on `CONNECTION_ERROR` and `game_loop` ticks degrade to multi-second stalls instead of entering a quieter degraded mode.
Outdated backend self-checks: replace or modernize `test_backend.sh` so it reflects the current runtime startup path rather than an older config-only check.
Frontend task panel collapse: add per-task expand/collapse and default completed-expert/details sections to collapsed so long-lived tasks do not become unreadable; queue this behind the current stability/testing work unless the implementation is trivially isolated.
Capability prompt truth alignment: make capability-facing context distinguish prereq-satisfied from buildable-now, and surface stale-world, disabled-gateway, low-power, and queue-blocked truth as first-class blockers instead of burying them in generic headers.
Unit-reservation contract surfacing: promote `UnitReservation` state from kernel bookkeeping into capability/runtime/debug surfaces, and tighten cancel/fulfill semantics without removing the current fast-path bootstrap path.
Task triage/debug bundle follow-up: expose deterministic `phase` / `waiting_reason` / `blocker` / `highlights` summaries in task list and replay flows so diagnostics answer “what is this task doing now?” before forcing raw log reading.
Knowledge/planner truth cleanup: keep aligning `experts/knowledge.py` / `experts/planners.py` with the normalized demo capability truth so soft strategy does not overclaim unsupported faction/buildability semantics.
Historical task debug bundle follow-up: keep improving replay/diagnostics so one task can be triaged from structured highlights instead of raw log scrolling.
Test-signal audit follow-up: broader capability/diagnostics E2E coverage still remains, but the bootstrap smoke / adjutant mock-surface gap and several stale assertion surfaces are now closed.
Docs hygiene follow-up: archive stale slice/audit notes in `docs/yu` and keep only actively referenced execution docs at the top level.

## Blocked (optional)
