# Round 3 scenario audit of `design.md`

## Verdict

**A-D now have zero hard blockers on their mainline paths.**

That is the main result of this round.

I re-ran A-E and added F. The spec is now substantially more executable for direct player-command scenarios. The remaining blockers are concentrated in:

1. **Scenario E**: the no-repair-facility branch is still not fully specified
2. **Scenario F**: passive defense-task creation authority and attack-vs-defense resource competition policy are still not specified

So the current picture is:

- **A. 生产5辆重型坦克**: zero hard blockers
- **B. 所有部队撤退回基地**: zero hard blockers
- **C. 别追太远**: zero hard blockers
- **D. 包围右边那个基地**: zero hard blockers
- **E. 修理我的坦克，然后继续进攻**: 1 blocker remains
- **F. 敌人在攻击我的基地！**: 2 blockers remain

## Scenario A: “生产5辆重型坦克”

### Trace

1. Kernel creates `Task(kind="background")`.
2. Task Agent wakes with context packet.
3. Task Agent optionally resolves queue availability:
   - `query_world(query_type="production_queues", params={"unit_type":"2tnk"})`
4. Task Agent creates the job:
   - `start_job(expert_type="EconomyExpert", config=EconomyJobConfig(unit_type="2tnk", count=5, queue_type="vehicle_factory", repeat=False))`
5. Kernel binds `ResourceNeed(kind="production_queue")`.
6. EconomyJob issues production via GameAPI.
7. Each unit completion triggers:
   - `Event(type="PRODUCTION_COMPLETE", ...)`
   - EconomyJob emits `ExpertSignal(kind="progress", summary="已完成 1/5", ...)`
8. If money/power/factory availability breaks:
   - EconomyJob enters `waiting`, not `failed`
9. If all 5 complete:
   - EconomyJob emits `ExpertSignal(kind="task_complete", result="succeeded", data={"completed":5})`
10. Task Agent wakes and finishes the task:
   - `complete_task(result="succeeded", summary="5辆重型坦克已完成")`

### Blocker status

**No hard blocker found.**

Residual risk:

- queue-selection heuristics are still implementation-level, not deeply specified
- but the runtime path is now clear enough to implement

## Scenario B: “所有部队撤退回基地”

### Trace

1. Kernel creates a new `Task(kind="managed")`.
2. Task Agent wakes with context packet.
3. Task Agent resolves:
   - `query_world(query_type="base_position", params={"owner":"self"})`
   - `query_world(query_type="actors", params={"owner":"self","category":["infantry","vehicle"]})`
4. Task Agent cancels conflicting tasks that currently own combat units:
   - `cancel_tasks(filters={"expert_type":"CombatExpert"})`
   - and, if needed, additional `cancel_tasks(filters={"expert_type":"ReconExpert"})`
5. Task Agent starts retreat movement:
   - `start_job(expert_type="MovementExpert", config=MovementJobConfig(target_position=base_pos, actor_ids=[...], move_mode="retreat", arrival_radius=10))`
6. MovementJob autonomously moves units home.
7. On arrival:
   - `ExpertSignal(kind="task_complete", result="succeeded", data={"returned_actor_ids":[...]})`
8. Task Agent wakes:
   - `complete_task(result="succeeded", summary="部队已撤回基地")`

### Blocker status

**No hard blocker found.**

Residual risk:

- the exact filter policy for “所有部队” is still a design choice
- but the tool surface now supports the required bulk-cancel plus explicit retreat executor path

## Scenario C: “别追太远”

### Trace

1. Kernel creates `Task(kind="constraint")`.
2. Task Agent wakes with context packet.
3. Task Agent creates the live constraint:
   - `create_constraint(kind="do_not_chase", scope="expert_type:CombatExpert", params={"max_chase_distance":20}, enforcement="clamp")`
4. Existing CombatJobs read matching active constraints from WorldModel every tick.
5. If `clamp`, they limit chase distance locally.
6. If instead Task Agent chose `enforcement="escalate"`, a violating job would emit:
   - `ExpertSignal(kind="decision_request", summary="即将超出追击距离", decision={...})`
7. Task Agent could then:
   - `patch_job(...)`
   - `abort_job(...)`
   - or later `remove_constraint(...)`

### Blocker status

**No hard blocker found.**

The previous `create_constraint` vs `enforcement` gap is closed.

## Scenario D: “包围右边那个基地”

### Trace

1. Kernel creates `Task(kind="managed" or "supervised")`.
2. Task Agent wakes with context packet.
3. Task Agent resolves the target:
   - `query_world(query_type="resolve_target", params={"raw_text":"右边那个基地"})`
4. If target certainty is low, Task Agent starts recon first:
   - `start_job(expert_type="ReconExpert", config=ReconJobConfig(...))`
5. ReconJob autonomously scouts.
6. On confirmation:
   - `ExpertSignal(kind="task_complete", result="succeeded", data={"base_pos":(...), "approaches":[...]})`
7. Task Agent wakes and, in a single wake, can issue multiple tool calls:
   - `query_world(query_type="available_forces", params={...})`
   - `start_job(expert_type="CombatExpert", config=CombatJobConfig(target_position=..., engagement_mode="surround", ...))`
   - `start_job(expert_type="CombatExpert", config=CombatJobConfig(target_position=..., engagement_mode="surround", ...))`
   - optional third flank
8. If one flank is destroyed:
   - relevant job emits `ExpertSignal(kind="resource_lost" | "task_complete", result="failed", ...)`
9. Task Agent wakes and adapts:
   - `patch_job(...)`
   - or additional `start_job(...)`
   - or `complete_task(result="partial"|...)`

### Blocker status

**No hard blocker found.**

This remains the strongest example of the new architecture working as intended.

### LLM wake count

Minimum mainline:

1. initial wake: resolve target + start recon
2. wake on recon completion: start 2-3 combat jobs

Then add extra wakes only for major adverse events or strategic adaptation.

## Scenario E: “修理我的坦克，然后继续进攻”

### Trace

1. Kernel creates `Task(kind="managed")`.
2. Task Agent wakes with context packet.
3. Task Agent resolves damaged tanks:
   - `query_world(query_type="damaged_actors", params={"owner":"self","category":"vehicle"})`
4. Task Agent resolves repair facilities:
   - `query_world(query_type="repair_facilities", params={"owner":"self"})`
5. If a facility exists, Task Agent creates the repair movement job:
   - `start_job(expert_type="MovementExpert", config=MovementJobConfig(target_position=repair_facility_pos, actor_ids=[tank_id], move_mode="move", arrival_radius=6))`
6. MovementExpert reaches facility and issues the repair-related GameAPI command.
7. On repair completion:
   - `ExpertSignal(kind="task_complete", result="succeeded", data={"repaired_actor_ids":[tank_id]})`
8. Task Agent wakes and resumes offense:
   - either `resume_job(old_combat_job_id)`
   - or `start_job(expert_type="CombatExpert", config=...)`

### Remaining blocker

**1 blocker remains:** the no-repair-facility branch is still not fully specified.

The mapping table says:

> 无维修设施 → Task Agent 通过 query_world 发现 → 告知玩家或降级处理。

That is directionally useful, but not deterministic enough to implement from spec alone. The spec still does not say which of these is the standard behavior:

- fail the task
- continue attack without repair
- wait for facility / future opportunity
- complete as partial with explanation

### Otherwise

The mainline repair-then-resume path is now clear enough.

## Scenario F: “敌人在攻击我的基地！”

### Trace

1. This is **not** a player command. It starts from:
   - `Event(type="BASE_UNDER_ATTACK", ...)`
2. WorldModel emits the event.
3. Kernel routes the event to related Task Agents and Jobs.
4. A defense response must be created somehow.

### Remaining blockers

**2 blockers remain here.**

#### F1. Defense-task creation authority is unspecified

The spec still does not define who is allowed/required to create the defensive task when `BASE_UNDER_ATTACK` occurs:

- does Kernel auto-create a high-priority defense Task?
- does Kernel only route the event to existing Task Agents and wait?
- does it require player confirmation?
- does one special standing “home defense” Task exist already?

For a passive event-driven response, this is a core missing authority decision.

#### F2. Attack-vs-defense coexistence / resource competition policy is unspecified

Even if a defense Task is created, the spec does not define the policy for competing with currently running attack tasks:

- does defense get an automatic higher priority?
- should Kernel preempt attack jobs immediately?
- does Task Agent for the attack task get a chance to negotiate/reduce commitment?
- can attack and defense coexist with partial resource split?

The Kernel has generic priority/preemption machinery, but no policy for this specific event-triggered strategic conflict.

### What is clear already

If Wang later chooses an authority policy, the rest of the machinery is mostly present:

- event arrives
- Task Agent can be awakened
- `query_world` can inspect threats and available defenders
- `start_job(CombatExpert, engagement_mode="hold"/"assault")` can likely express defensive jobs
- `cancel_tasks(...)` can free resources if required

But the authority/policy step is still missing.

## Bottom line

This round is a real step forward:

- **A-D now read as implementation-ready on their mainline paths**
- **E is almost there, but the no-repair-facility branch still needs one explicit policy**
- **F exposes a new class of gap: passive event-triggered task creation and cross-task strategic arbitration policy**

If Wang wants the shortest actionable summary:

1. declare one deterministic fallback for “repair requested but no repair facility exists”
2. declare who auto-creates defense tasks on `BASE_UNDER_ATTACK`
3. declare default priority/preemption policy between active attack tasks and emergency defense tasks
