# yu Knowledge Base

- Deliverables explicitly assigned by Wang go under `docs/wang/` (or `docs/wang/archive/` for archived investigation artifacts); `docs/yu/` is reserved for yu's own agent state and yu-only files.
- Base `TaskAgent` still has no native `push_player_response()` intake; Adjutant reply E2E currently needs a small test-side adapter to re-inject `PlayerResponse` into the agent wake loop.
