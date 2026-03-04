# Audit of `design.md` with 4 scenario walkthroughs

## Verdict

This rewrite is much cleaner architecturally, but it is **not yet fully implementable from spec alone**. I found **7 concrete blockers/gaps** that show up when walking the four requested scenarios.

The core pattern is:

- the high-level architecture is coherent
- the event-driven Brain/Job split is clear
- but the **runtime control contract is still too thin** for batch operations, terminal semantics, constraints, and production/economy behavior

## Findings

### 1. Task Agent tool contract is missing

Relevant lines:
- `Task Agent` creates/configures Jobs through tool use: `docs/wang/design.md:162-169`
- control surface lists `start / patch / pause / resume / abort`: `docs/wang/design.md:178`
- examples use `start_job`, `patch_job`, `abort_job`, `cancel_task`: `docs/wang/design.md:277-287`, `docs/wang/design.md:324`, `docs/wang/design.md:347`, `docs/wang/design.md:356`

Problem:

- The spec never defines the actual Task Agent tool API.
- Missing for each tool:
  - full parameters
  - return shape
  - error shape
  - whether calls are idempotent
  - whether multiple tool calls are allowed in one LLM wake
- This matters immediately because the examples rely on follow-up operations by `job_id`, but `start_job(...)` is not specified to return a `job_id`, and no other contract says how the Task Agent learns it.

Why this blocks implementation:

- We cannot implement the Task Agent loop or tool schemas without inventing core runtime behavior.

### 2. Terminal result semantics are inconsistent / incomplete

Relevant lines:
- `Task.status`: `docs/wang/design.md:57-66`
- `Job.status`: `docs/wang/design.md:68-77`
- `ExpertSignal` schema: `docs/wang/design.md:118-126`
- success path uses `abort_job(job_id)` to finish successfully: `docs/wang/design.md:323-326`
- preempt path uses `Signal(task_complete, result=aborted)`: `docs/wang/design.md:367-368`

Problem:

- There is no explicit `Outcome` / `JobResult` / terminal payload model anymore.
- `ExpertSignal` does not include `result`, but the preempt example uses `result=aborted`.
- `Job.status` only has `running / waiting / completed / aborted`, while `Task.status` distinguishes `succeeded / partial / failed / aborted`.
- The normal success path says the Task Agent calls `abort_job(job_id)` to reclaim resources after success, which collapses “successful completion” and “forced abort” into one control path.

Why this blocks implementation:

- Kernel and Task Agent do not have one deterministic terminal contract for:
  - success
  - failure
  - abort
  - preempt
  - partial completion

### 3. Constraint creation and propagation are underspecified

Relevant lines:
- `Task.kind` includes `constraint`: `docs/wang/design.md:62`
- `Constraint` model: `docs/wang/design.md:109-116`
- `WorldModel` stores runtime constraints: `docs/wang/design.md:181-186`
- escalation rule mentions violating a constraint: `docs/wang/design.md:216-223`

Problem:

- The spec defines a `Constraint` data model, but not the runtime API that creates one.
- No Task Agent tool like `create_constraint(...)` or `update_constraint(...)` is defined.
- No propagation mechanism is defined for how existing Jobs discover newly added constraints.
- No enforcement semantics are defined:
  - hard stop?
  - patch behavior?
  - emit `decision_request`?
  - auto-abort?

Why this blocks implementation:

- Scenario C cannot be implemented from the current spec alone.

### 4. The resource model is too actor-centric for production/economy

Relevant lines:
- `EconomyJobConfig`: `docs/wang/design.md:93-97`
- `ResourceNeed.kind = actor / production_queue`: `docs/wang/design.md:99-105`
- Kernel “持续满足 / 不足降级运行”: `docs/wang/design.md:107`, `docs/wang/design.md:156`
- `Event.type` includes `PRODUCTION_COMPLETE`: `docs/wang/design.md:128-135`

Problem:

- `ResourceNeed` says `production_queue`, but the rest of the resource semantics are written like actor replacement.
- There is no defined model for economy-side degraded resources:
  - cash shortage
  - power shortage
  - blocked queue
  - factory destroyed
  - queue contention
- `PRODUCTION_COMPLETE` exists as an event, but there is no progress accounting contract:
  - does the EconomyJob decrement remaining count?
  - does it signal every unit completion?
  - how is partial completion represented if only 3/5 tanks are produced?

Why this blocks implementation:

- Scenario A stalls halfway through production lifecycle design.

### 5. No global / bulk control contract for cross-task commands

Relevant lines:
- Kernel cancel API is task-specific: `docs/wang/design.md:160`
- Task Agent control surface is job-scoped: `docs/wang/design.md:178`

Problem:

- The only explicit cancel path is `Kernel.cancel(task_id)`.
- There is no selector-based or bulk operation API for:
  - all combat jobs
  - all jobs holding actors
  - all units in army
  - all tasks in a category
- This becomes critical for commands like “所有部队撤退回基地”.

Why this blocks implementation:

- Scenario B requires a global task/job selector or a mass handoff mechanism that the spec does not define.

### 6. Multi-job coordination is described conceptually, but not represented in runtime data

Relevant lines:
- Task Agent coordinates multiple Jobs and timing dependencies: `docs/wang/design.md:164-167`
- Context packet includes current jobs and recent signals: `docs/wang/design.md:200-208`
- Task Agent implementation is `event → inject context → 一次 tool_use → sleep`: `docs/wang/design.md:225-227`

Problem:

- There is no explicit runtime representation for:
  - job dependencies
  - barriers / waits
  - “when A finishes, start B”
  - grouped subgoals
  - phase transitions inside one Task
- The “一次 tool_use” wording is also ambiguous for multi-job orchestration:
  - can one wake issue 3 `start_job` calls?
  - or exactly one tool call per wake?

Why this blocks implementation:

- Scenario D needs structured coordination, not just ad hoc prompt reasoning over free text context.

### 7. Spatial reference / target resolution path is missing

Relevant lines:
- Task Agent “理解玩家意图（接收 raw_text + WorldModel 上下文）”: `docs/wang/design.md:163`
- context packet only includes summarized world state: `docs/wang/design.md:200-208`

Problem:

- The clean rewrite removed any explicit resolver / target-resolution mechanism.
- The spec never defines how the Brain resolves:
  - “右边那个基地”
  - “所有部队”
  - “基地”
  - “重型坦克” if there are multiple production queues / tech constraints
- No WorldModel query tool for the Task Agent is specified, even though complex spatial reference resolution clearly needs one.

Why this blocks implementation:

- Scenarios B and D both require target resolution the spec does not currently define.

## Scenario walkthroughs

## Scenario A: “生产5辆重型坦克”

### Trace

1. Kernel creates `Task(kind="background")`.
2. Task Agent wakes with raw text + context packet.
3. Task Agent likely calls:
   - `start_job(expert_type="EconomyExpert", config=EconomyJobConfig(unit_type="2tnk", count=5, queue_type=?, repeat=False))`
4. Kernel creates `EconomyJob`.
5. Kernel allocates `ResourceNeed(kind="production_queue")`.
6. EconomyJob ticks every 5s and monitors production.
7. `PRODUCTION_COMPLETE` events arrive.
8. EconomyJob or Kernel must track remaining count until 5 are complete.
9. Task Agent marks task succeeded / partial / failed.

### Where the spec stops being enough

1. `queue_type` selection is unspecified.
   - If multiple factories exist, the spec does not say whether the Task Agent chooses one, the Kernel chooses one, or EconomyJob binds all compatible queues.
2. EconomyJob `ResourceNeed` semantics are unspecified.
   - `production_queue` is defined as a kind, but no queue-binding lifecycle is defined.
3. Progress accounting is unspecified.
   - The spec does not say whether each `PRODUCTION_COMPLETE` emits a `progress` signal, updates `count_remaining`, or is only observed through WorldModel polling.
4. Midway cash shortage is unspecified.
   - “不足降级运行” is too vague for economy queues.
   - There is no contract for waiting-on-money vs partial completion vs blocked signal.
5. Terminal semantics are unspecified.
   - If 3/5 tanks are produced and then the factory dies, we cannot determine from the spec alone whether the Task becomes `partial`, `failed`, or remains `waiting`.

## Scenario B: “所有部队撤退回基地”

### Trace

1. Kernel creates a new Task from the retreat command.
2. Task Agent interprets this as a global army-wide override.
3. Existing combat-related Jobs across multiple Tasks must release or surrender units.
4. A retreat-capable controller must take ownership of those units.
5. Units move back to base while respecting resource conflicts and task status.

### Where the spec stops being enough

1. There is no global selector/control API.
   - `Kernel.cancel(task_id)` is task-scoped only.
   - No “cancel all combat jobs” or “rebind all owned actors” API exists.
2. There is no defined retreat executor.
   - The spec names `ReconJob`, `CombatJob`, and `EconomyJob`, but nothing like `RetreatJob` / `MovementJob`.
   - It is unclear whether retreat is a CombatJob mode, a new Expert type, or a Task Agent macro that rewrites all current jobs.
3. Resource reassignment is undefined.
   - All units are already bound to different Jobs.
   - The spec has preemption rules for one resource conflict, but not a mass cross-task evacuation command.
4. “所有部队” resolution is undefined.
   - No target-selection or actor-selection query API is defined for the Brain.

## Scenario C: “别追太远” (Constraint)

### Trace

1. Kernel creates `Task(kind="constraint")`.
2. Task Agent interprets user intent as a chase-limit constraint.
3. A `Constraint(kind="do_not_chase", scope=?, params={max_chase_distance: ...})` must be created.
4. Existing CombatJobs must observe the new constraint.
5. When a CombatJob is about to exceed chase distance, it must adapt or escalate.

### Where the spec stops being enough

1. Constraint creation API is missing.
   - There is no tool that turns LLM intent into a live `Constraint`.
2. Scope is too weakly defined.
   - Only `global / task_id` exists.
   - For “别追太远”, do we mean all combat jobs globally, all jobs in the issuing task, or only offensive jobs?
3. Propagation is missing.
   - The spec never says how running CombatJobs learn that a new constraint has appeared.
4. Enforcement semantics are missing.
   - If a job is about to violate the constraint, do we:
     - clamp movement locally?
     - emit `decision_request`?
     - abort the job?
     - auto-patch `max_chase_distance`?

## Scenario D: “包围右边那个基地” (Complex multi-Job)

### Trace

1. Kernel creates `Task(kind="managed")`.
2. Task Agent must resolve “右边那个基地”.
3. Task Agent starts a recon job first if base position is uncertain.
4. After the base is confirmed, Task Agent must create 2-3 combat jobs for different flanks.
5. Task Agent coordinates timing so flanks converge together.
6. If one flank is destroyed, Task Agent must adapt the plan.

### Where the spec stops being enough

1. “右边那个基地” resolution is missing.
   - No resolver or Brain-side world query tool is defined.
2. Multi-job creation semantics are ambiguous.
   - The runtime description says `event → inject context → 一次 tool_use → sleep`.
   - If literal, one wake cannot create recon + 2-3 combat jobs or even 2-3 combat jobs after recon.
   - The spec must say whether one LLM turn may issue multiple tool calls.
3. Combat flank differentiation is missing.
   - `CombatJobConfig` has `target_position` and `engagement_mode="surround"`, but no per-flank role/sector/approach vector field.
   - Three surround jobs with identical config are not operationally distinct.
4. Coordination state is missing.
   - The Task Agent is said to coordinate timing, but no dependency/barrier model exists.
   - We need at least one explicit way to represent “wait until recon confirms target” and “launch flank B only when flank A is in position”.
5. Adaptation after flank loss is underdefined.
   - A `resource_lost` or `task_complete` signal might wake the Brain, but the spec does not define enough coordination state to know whether it should:
     - reinforce the failed flank
     - collapse to a 2-prong attack
     - abort surround and switch to assault

### LLM call count for Scenario D

What is clear from the spec:

- 1 LLM call at task start
- at least 1 more when recon finds or disambiguates the base
- probably 1 more if a flank is destroyed and the event crosses escalation threshold

What is not clear from the spec:

- whether the “spawn 2-3 combat jobs” step is one LLM wake with multiple tool calls or several separate wakes

So the exact LLM call count is **not currently derivable from spec alone**.

## Bottom line

The architecture direction is correct, but the spec still needs the following before I would call it implementation-ready:

1. explicit Task Agent tool schemas and return contracts
2. one terminal result model shared by Job / Task / Signal paths
3. a real constraint lifecycle
4. production/economy runtime semantics
5. global/bulk control semantics for cross-task commands
6. explicit multi-job coordination primitives
7. a target-resolution / world-query path for the Brain
