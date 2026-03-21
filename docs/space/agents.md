# Space Agent — Knowledge Base

## Project Overview
- THE-Seed-OpenRA: AI agent for Red Alert (OpenRA) game, autonomous decision-making & operation
- Two-phase architecture: Legacy (FSM via the-seed) + Next-Gen (independent agent modules)
- Current dev focus: Next-Gen modules under `agents/`

## Architecture

### Communication Chain
```
Web Console (port 8000) ↔ WebSocket (ws://127.0.0.1:8090) ↔ main.py (Console Bridge) ↔ OpenRA API (port 7445, TCP JSON) ↔ OpenRA Game
```

### Core Modules
| Module | Path | Role |
|---|---|---|
| main.py | `/main.py` | Legacy entry, Console Bridge, integrates NLU/enemy/strategy |
| Combat Agent | `agents/combat/` | Squad micro-ops, LLM-driven tactical decisions |
| Economy Agent | `agents/economy/` | Auto resource/building/production via heuristic state machine |
| Strategy Agent | `agents/strategy/` | Global strategy via LLM (Doubao-Pro-32k), commands combat+economy |
| NLU Gateway | `agents/nlu_gateway.py` | Natural language command routing (intent model + LLM fallback) |
| OpenRA API | `openra_api/` | Unified Socket client, macro actions, intel service, job system |
| OpenRA State | `openra_state/` | Intelligence aggregation, zone analysis, visualization |
| Tactical Core | `tactical_core/` | Potential field micro, cooperative retreat, hard interrupts |
| NLU Pipeline | `nlu_pipeline/` | Intent model training pipeline (data→label→train→eval→release) |
| Web Console | `web-console/` | Browser-based monitoring dashboard |

### Key Interfaces
- Combat: `set_company_order(company_id, order_type, params)` — upstream control
- Economy: `set_active(bool)` — runtime toggle
- Tactical Core: `BiodsEnhancer.enhance_execute(api_client, pairs)` — micro enhancement
- Intel: `IntelligenceSink.update_intelligence(key, value)` — state injection
- Socket API: Full spec in `socket-apis.md`

## Conventions
- `OpenCodeAlert/` (game C# source) and `the-seed/` (agent framework) are also owned by the user, can read/modify when needed — just be mindful of size
- Each next-gen module is standalone with own Socket client, designed for future framework integration
- LLM: Doubao-Pro-32k via OpenAI SDK
- Tech stack: Python 3.12, uv, WebSocket, Socket JSON protocol
- Config loaded via `the-seed` `load_config()`, secrets in `.env`
- Factions: Soviet (default), Allies — configurable via `OPENRA_FACTION` env var
