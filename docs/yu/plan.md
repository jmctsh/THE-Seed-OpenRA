## Current
Coordinator/runtime contract cleanup: reduce remaining stringly-typed capability/coordinator wording drift across `kernel` / `adjutant` / `task_agent`, now that capability truth exposure and atomic adjutant snapshot reads are landed.

## Queue
Typed runtime/coordinator snapshot follow-up: keep collapsing `main.py` / `adjutant` / `world_model` runtime assembly onto shared typed views instead of ad hoc dict shaping.
Historical task debug bundle follow-up: keep improving replay/diagnostics so one task can be triaged from structured highlights instead of raw log scrolling.

## Blocked (optional)
