# Round 2 scenario audit of `design.md`

## Verdict

The updated spec closes most of the previous structural gaps. But **A-D are not zero blockers** yet. I still see **4 concrete blockers/gaps** after re-running the four original scenarios and adding scenario E.

Current status by scenario:

- **A. 生产5辆重型坦克**: still blocked by deferred economy/runtime details
- **B. 所有部队撤退回基地**: still blocked by missing retreat-capable executor/config
- **C. 别追太远**: almost closed, but one local spec gap remains in constraint creation
- **D. 包围右边那个基地**: mainline path is now implementable from spec alone
- **E. 修理我的坦克，然后继续进攻**: blocked by missing repair-capable executor/config and no-repair-facility fallback semantics

## Remaining blockers

### 1. Economy / production runtime semantics are still deferred

Relevant lines:
- `EconomyJobConfig`: `docs/wang/design.md:93-97`
- `ResourceNeed(kind=production_queue)`: `docs/wang/design.md:99-107`
- `Event.type` includes `PRODUCTION_COMPLETE`: `docs/wang/design.md:130-135`

Problem:

- The spec still does not define how EconomyJob tracks progress from 0/5 to 5/5.
- It does not define whether each unit completion emits a `progress` signal.
- It does not define what “不足降级运行” means for production queues:
  - out of money
  - power shortage
  - factory destroyed
  - queue blocked by another production task
- It also does not define the terminal policy for partial completion, even though `Task.status` has `partial`.

Impact:

- Scenario A still cannot be completed from spec alone.

### 2. No retreat-capable Job/Expert is defined

Relevant lines:
- available job families are still only implied by Recon / Combat / Economy: `docs/wang/design.md:47-51`, `docs/wang/design.md:80-97`
- `cancel_tasks(filters)` now exists: `docs/wang/design.md:167`, `docs/wang/design.md:193`

Problem:

- The new bulk-control API solves the “cancel all combat tasks” part.
- But the spec still has no `RetreatExpert`, `MovementExpert`, or retreat mode in `CombatJobConfig`.
- So after cancelling existing combat tasks, the design still has no defined executor/config for “move all relevant units back to base”.

Impact:

- Scenario B still stops halfway through: we can free units, but we cannot rebind them to a spec-defined retreat controller.

### 3. `create_constraint` tool signature is missing `enforcement`

Relevant lines:
- `Constraint.enforcement` is required by the model: `docs/wang/design.md:109-121`
- tool table: `create_constraint | kind, scope, params`: `docs/wang/design.md:184-193`

Problem:

- The Constraint model now clearly distinguishes `enforcement=clamp|escalate`.
- But the only creation tool does not expose `enforcement` as an argument.
- That leaves one unresolved guess:
  - is `enforcement` hidden inside `params`?
  - is there a default?
  - must Task Agent always create clamping constraints?

Impact:

- Scenario C is almost closed, but not fully spec-complete until constraint creation can deterministically choose clamp vs escalate.

### 4. No repair-capable Job/Expert is defined, and no “no repair facility” fallback is specified

Relevant lines:
- only Recon / Combat / Economy configs are defined: `docs/wang/design.md:80-97`
- Task Agent can sequence Jobs through signals and multiple tool calls: `docs/wang/design.md:172-179`, `docs/wang/design.md:223-231`

Problem:

- The updated spec is now good enough to express the sequencing idea behind “repair first, then continue attack”.
- But there is still no `RepairExpert`, `RepairJobConfig`, or reuse of another expert family that clearly covers:
  - finding repair facility
  - moving damaged tank there
  - waiting for repair completion
  - rejoining attack
- There is also no spec-defined fallback if no repair facility exists.

Impact:

- Scenario E is still blocked.

## Scenario walkthroughs

## Scenario A: “生产5辆重型坦克”

### Trace

1. Kernel creates `Task(kind="background")`.
2. Task Agent wakes with context packet.
3. Likely first tool call:
   - `query_world(query_type="production_queues", params={"unit_type":"2tnk"})`
4. Task Agent selects queue and calls:
   - `start_job(expert_type="EconomyExpert", config=EconomyJobConfig(unit_type="2tnk", count=5, queue_type="vehicle_factory", repeat=False))`
5. Kernel creates EconomyJob and binds `ResourceNeed(kind="production_queue")`.
6. EconomyJob ticks every 5s and issues production through GameAPI.
7. `PRODUCTION_COMPLETE` events arrive from WorldModel.
8. EconomyJob and/or Task Agent track progress until task is complete.

### Signals / tools expected

- `query_world(...)`
- `start_job(...)`
- likely repeated `ExpertSignal(kind="progress", ...)` on unit completion
- final `ExpertSignal(kind="task_complete", result="succeeded" | "partial" | "failed", data=...)`
- `complete_task(...)`

### Remaining blocker

The spec still does not define the progress/degraded-resource/partial-completion behavior of EconomyJob. This remains a real blocker.

## Scenario B: “所有部队撤退回基地”

### Trace

1. Kernel creates a new Task from the retreat command.
2. Task Agent wakes with context packet.
3. Task Agent resolves base position:
   - `query_world(query_type="base_position", params={"owner":"self"})`
4. Task Agent cancels current combat tasks:
   - `cancel_tasks(filters={"expert_type":"CombatExpert"})`
5. Freed units now need a retreat controller that sends them back to base.

### Signals / tools expected

- `query_world(...)`
- `cancel_tasks(filters=...)`
- then one or more `start_job(...)` calls for retreat/movement jobs

### Remaining blocker

The bulk cancellation part is now spec-defined, but the retreat execution part is not. There is still no defined Job/Expert/config for “retreat all these units to base”.

## Scenario C: “别追太远”

### Trace

1. Kernel creates `Task(kind="constraint")`.
2. Task Agent wakes with context packet.
3. Task Agent creates the constraint:
   - `create_constraint(kind="do_not_chase", scope="expert_type:CombatExpert", params={"max_chase_distance":20, ...})`
4. Existing CombatJobs read matching constraints from WorldModel every tick.
5. If `enforcement=clamp`, they locally clamp chase behavior.
6. If `enforcement=escalate`, they emit:
   - `ExpertSignal(kind="decision_request", summary="即将超出追击距离", ...)`
7. Task Agent may patch/abort/reconfigure Jobs if needed.

### Signals / tools expected

- `create_constraint(...)`
- possible `ExpertSignal(kind="decision_request", ...)`
- `patch_job(...)` or `abort_job(...)`
- optional `remove_constraint(...)` later

### Remaining blocker

The lifecycle is otherwise coherent now, but the creation path still lacks an explicit `enforcement` argument. Without that, the spec still leaves one required behavior choice implicit.

## Scenario D: “包围右边那个基地”

### Trace

1. Kernel creates `Task(kind="managed")`.
2. Task Agent wakes with context packet.
3. Task Agent resolves target:
   - `query_world(query_type="resolve_target", params={"raw_text":"右边那个基地"})`
4. If target position is uncertain, Task Agent starts recon first:
   - `start_job(expert_type="ReconExpert", config=ReconJobConfig(...))`
5. ReconJob runs autonomously and eventually emits:
   - `ExpertSignal(kind="task_complete", result="succeeded", data={"base_pos": (...)})`
6. Task Agent wakes again and, in one wake, can now issue multiple tool calls:
   - `query_world(query_type="available_forces", params={...})`
   - `start_job(expert_type="CombatExpert", config=CombatJobConfig(target_position=..., engagement_mode="surround", ...))`
   - `start_job(expert_type="CombatExpert", config=CombatJobConfig(target_position=..., engagement_mode="surround", ...))`
   - optional third flank job
7. One flank later gets destroyed:
   - related CombatJob emits `ExpertSignal(kind="resource_lost" | "task_complete", result="failed", ...)`
8. Task Agent wakes and adapts:
   - `patch_job(...)` remaining flanks
   - and/or `start_job(...)` reinforcement
   - and/or `complete_task(result="partial"|...)`

### Signals / tools expected

- `query_world(...)`
- `start_job(...)` for recon
- `ExpertSignal(kind="task_complete", result="succeeded", data={"base_pos":...})`
- multiple `start_job(...)` in one wake for flank jobs
- later `resource_lost` / `task_complete`
- `patch_job(...)` / additional `start_job(...)` / `complete_task(...)`

### Blocker status

**No hard blocker found for the mainline scenario.**

The updated spec is now sufficient to trace the path:

- target resolution via `query_world`
- recon-first if needed
- multiple tool calls in one wake
- adaptation on later signals

Residual risk:

- coordination is still LLM-memory-driven rather than represented by explicit runtime primitives
- but per Wang’s note, that has been deferred to implementation rather than spec

### LLM call count

Minimum plausible count from spec:

1. initial wake to resolve target and start recon
2. wake on recon completion to start 2-3 combat jobs
3. optional wake if a flank is destroyed and adaptation is needed

So the mainline is **2 LLM wakes**, with **+1 or more** on major adverse events.

## Scenario E: “修理我的坦克，然后继续进攻”

### Trace

1. Kernel creates `Task(kind="managed")`.
2. Task Agent wakes with context packet.
3. Task Agent queries damaged tanks:
   - `query_world(query_type="damaged_actors", params={"owner":"self","category":"vehicle"})`
4. Task Agent queries repair facilities:
   - `query_world(query_type="repair_facilities", params={"owner":"self"})`
5. If repair is possible, Task Agent should start a repair job first.
6. On repair completion signal, Task Agent should start/resume the attack job.

### Signals / tools expected

- `query_world(...)` for damaged tanks
- `query_world(...)` for repair facilities
- `start_job(...)` for repair
- `ExpertSignal(kind="task_complete", result="succeeded", data={"repaired_actor_ids":[...]})`
- then `start_job(...)` or `resume_job(...)` for attack continuation

### Remaining blockers

1. There is no `RepairExpert` / `RepairJobConfig` in the current spec.
2. There is no clearly defined alternative executor such as `MovementExpert`.
3. If no repair facility exists, the spec does not define whether the Task Agent should:
   - fail immediately
   - skip repair and continue attack
   - wait for facility / MCV
   - mark partial

### Sequential dependency itself

The “then” part is now conceptually workable from spec alone:

- do repair first
- wait for repair job terminal signal
- then start/resume combat

So the sequencing mechanism is no longer the blocker. The blocker is the missing repair capability itself.

## Bottom line

Round 2 is a meaningful improvement. The following are now substantially fixed:

- Task Agent tool surface
- terminal signal/result shape
- bulk cancellation
- target resolution path
- multi-tool wakes

But I would still keep the spec open because **A-D are not yet zero blockers**:

1. economy/production semantics still block A
2. retreat executor still blocks B
3. `create_constraint` missing `enforcement` still leaves a local gap in C
4. repair executor/fallback still blocks E

D is the first complex multi-job scenario that now reads as genuinely implementable from the spec.
