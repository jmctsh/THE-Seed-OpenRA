## Current
Coordinator/runtime contract cleanup: reduce remaining stringly-typed capability/coordinator wording drift across `kernel` / `adjutant` / `task_agent`, now that capability truth exposure and atomic adjutant snapshot reads are landed.

## Queue
Typed runtime/coordinator snapshot follow-up: keep collapsing `main.py` / `adjutant` / `world_model` runtime assembly onto shared typed views instead of ad hoc dict shaping.
Knowledge/planner truth cleanup: keep aligning `experts/knowledge.py` / `experts/planners.py` with the normalized demo capability truth so soft strategy does not overclaim unsupported faction/buildability semantics.
Historical task debug bundle follow-up: keep improving replay/diagnostics so one task can be triaged from structured highlights instead of raw log scrolling.
Test-signal audit follow-up: trim false-green coverage and add runtime-oriented assertions where mocks currently hide important contract drift.
Docs hygiene follow-up: archive stale slice/audit notes in `docs/yu` and keep only actively referenced execution docs at the top level.

## Blocked (optional)
