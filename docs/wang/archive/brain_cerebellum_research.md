# Brain-Cerebellum Architecture Research for LLM + Expert Coordination

## Executive take

Across robotics, LLM agent runtimes, and game AI, the pattern is consistent:

- The **slow layer** handles intent interpretation, goal selection, policy changes, exception handling, and cross-module coordination.
- The **fast layer** owns closed-loop execution, local replanning, and reflexes.
- The interface between them is **event-driven**, not polling-driven.
- The high layer does **not** continuously choose primitive actions. It configures an autonomous executor, subscribes to signals, and intervenes only at decision boundaries.

For OpenRA, the best translation is:

- **Brain = Task Agent (LLM)**: plan, choose/configure Expert, subscribe to signals, revise strategy, supervise.
- **Cerebellum = Expert**: autonomous controller with its own local state machine / scorer / influence-map logic.
- **Kernel**: runtime and arbitration substrate.
- **WorldModel**: shared typed state, snapshots, and event source.

The architecture should look much closer to **3T / Nav2 / GOAP-style supervision** than to a ReAct loop where the LLM decides every move.

---

## 1. Robotics patterns

### 1.1 Subsumption: higher layers modulate, lower layers keep running

Rodney Brooks’ subsumption architecture decomposes robot control into behavior layers with increasing competence; higher layers can suppress lower-layer outputs, but lower layers continue to function and remain operational on their own. This gives robustness and keeps fast reactions local.  
Source: Brooks, *A Robust Layered Control System for a Mobile Robot* (1986), especially the layered-control description and the claim that lower layers continue running while higher layers interfere selectively.  
Link: https://faculty.washington.edu/minster/bio_inspired_robotics/research_articles/brooks_robust_layered_control_robot_ieeetransrobotautomat1986.pdf

**Adoptable pattern**

- Expert must retain its own reflexes and micro loop even when Brain is absent or slow.
- Brain should mostly send **suppression / bias / target / constraint** updates:
  - change search region
  - change engagement policy
  - cap chase distance
  - switch objective priority
- Brain should not replace the Expert’s inner control policy.

**Implication for OpenRA**

- A CombatExpert should keep dodging, focus-firing, retreating, regrouping, and re-pathing locally.
- The LLM should say things like “hold west ridge”, “do not overchase”, “harass harvesters only”, not “unit 57 step left”.

### 1.2 3T: planner, sequencer, skills

NASA/JSC’s 3T architecture explicitly separates deliberative planning from execution over real-time skills. The planner reasons at a high abstraction level; the situated sequencer handles immediate future control; real-time skills deal with the world continuously. Bonasso and Kortenkamp also note that letting the planner assume normality while the executing robot discovers abnormalities produces real-time behavior instead of long inactive planning delays.  
Sources:
- Bonasso and Kortenkamp, *Using a Layered Control Architecture to Alleviate Planning with Incomplete Information* (1996)  
  https://cdn.aaai.org/Symposia/Spring/1996/SS-96-04/SS96-04-001.pdf

**Adoptable pattern**

- Keep the Brain abstract and sparse.
- Put abnormality detection in the executing layer.
- Escalate only when abnormalities cross a semantic boundary.

**Best mapping**

- Planner: Task Agent
- Sequencer: Task runtime inside Kernel + Expert command contract
- Skills: Expert local behaviors / action emitters

This suggests OpenRA may eventually want not just Brain and Cerebellum, but a thin **sequencer / supervisor contract** between them:

- Brain chooses objective + parameters
- Expert executes and emits signals
- Kernel routes events, applies overrides, records state, and preserves ordering

### 1.3 ROS2 Nav2: behavior tree navigator orchestrates modular servers

Nav2’s official docs describe a behavior-tree navigator that orchestrates independent task servers such as planner and controller servers over ROS actions/services. The behavior tree can replan periodically, swap planners/controllers, and contextually change settings without embedding all low-level logic in one module.  
Sources:
- Nav2 overview  
  https://docs.nav2.org/
- Nav2 behavior trees  
  https://docs.nav2.org/behavior_trees/

Relevant mechanism:

- BT orchestrator owns the high-level flow.
- Planner/controller servers remain modular.
- Blackboard/shared state carries intermediate context like current path.
- The tree can change settings or select different algorithms based on context.

**Adoptable pattern**

- Brain should orchestrate Experts through a **typed control surface**, not ad hoc prompting.
- Shared context should be a structured per-task blackboard/state packet, not free-form conversation only.
- Expert parameters should be patchable at runtime:
  - `target_region`
  - `risk_tolerance`
  - `engagement_rules`
  - `search_pattern`
  - `retreat_threshold`

### 1.4 LLM-in-robotics pattern: LLM selects grounded skills, controllers execute

SayCan is one of the clearest examples of the desired split. The robot acts as the language model’s “hands and eyes”; the LLM provides high-level semantic knowledge, while value functions/skills ground executability in the current environment. The system iteratively selects the next skill by combining task relevance and execution feasibility.  
Source: SayCan project page / paper links  
https://say-can.github.io/

Inner Monologue adds the missing closed loop: language planning improves when the LLM receives environment feedback like success signals, scene descriptions, and human interaction.  
Source: Huang et al., *Inner Monologue: Embodied Reasoning through Planning with Language Models* (2022)  
https://arxiv.org/abs/2207.05608

**Adoptable pattern**

- Brain should choose among Experts and Expert modes using:
  - task relevance
  - current world feasibility
  - expert confidence / capability / risk
- Experts should return feedback in language-friendly but typed form.
- Closed-loop feedback should be selective, not raw telemetry spam.

---

## 2. LLM agent framework patterns

### 2.1 AutoGen Core: event-driven runtime, pub-sub topics, handoffs, intervention

AutoGen Core’s official docs frame agents as runtime-managed actors communicating through messages. It supports direct messaging and broadcast via topics/subscriptions, which the docs explicitly position as suitable for event-driven workflows where agents do not always know who will handle a message. AutoGen also documents handoff patterns and intervention handlers that can intercept publishes/sends for approval, termination, or supervision.  
Sources:
- Message and communication  
  https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/message-and-communication.html
- Topics and subscriptions  
  https://microsoft.github.io/autogen/0.4.6/user-guide/core-user-guide/core-concepts/topic-and-subscription.html
- Handoffs  
  https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/design-patterns/handoffs.html
- Intervention handlers  
  https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/cookbook/termination-with-intervention.html  
  https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/cookbook/tool-use-with-intervention.html

**Adoptable pattern**

- Every Task Agent should have its own event topic, e.g. `task/<task_id>`.
- Experts publish typed events to that topic.
- Brain subscribes only to the topics it owns.
- Kernel can attach intervention hooks:
  - block unsafe overrides
  - terminate stale tasks
  - trigger human approval
  - record traces / metrics

This is much closer to what we need than a chat loop.

### 2.2 CrewAI Flows: event-driven stateful orchestration

CrewAI Flows are explicitly “structured, event-driven workflows”; `@listen()` listeners react to prior outputs, and the framework exposes an event bus architecture through event listeners.  
Sources:
- Flows  
  https://docs.crewai.com/en/concepts/flows
- Event listeners  
  https://docs.crewai.com/en/concepts/event-listener

**Adoptable pattern**

- Brain runs should be resumed by events, not by periodic “ask LLM what now?”
- State should live outside the model in a task state object.
- Events should be first-class runtime entities, not just prompt text.

### 2.3 LangGraph: shared state, streaming updates, interrupts, checkpoints

LangGraph’s `StateGraph` uses shared state with reducers; compiled graphs support streaming of values, updates, messages, custom events, and debug events. Checkpointers persist graph state at every superstep, and interrupts support human-in-the-loop or controlled pauses.  
Sources:
- StateGraph shared state  
  https://langchain-ai.github.io/langgraphjs/reference/classes/langgraph.StateGraph.html
- CompiledGraph streaming / interrupts  
  https://langchain-ai.github.io/langgraphjs/reference/classes/langgraph.CompiledGraph.html
- Checkpointing  
  https://langchain-ai.github.io/langgraphjs/reference/modules/langgraph-checkpoint.html

**Adoptable pattern**

- Maintain a **task state object** outside the LLM:
  - current goal
  - expert config
  - latest world snapshot summary
  - last meaningful events
  - open decisions
  - intervention history
- Feed the Brain **state deltas** and selected event traces, not entire logs.
- Support interrupts for supervised tasks:
  - wait before irreversible action
  - ask user / higher authority
  - switch experts

---

## 3. Game AI patterns

### 3.1 F.E.A.R. GOAP: planner activates states and parameters, lower logic executes

Jeff Orkin’s F.E.A.R. architecture is directly relevant. The game used a planner to decouple goals and actions and to layer behaviors without manually wiring all transitions. In the talk, actions activate states and set parameters; the embedded state machines do not disappear, but are driven by higher-level planning choices. Shared working memory centralizes facts discovered during execution and supports replanning.  
Source: Orkin, *Three States and a Plan: The A.I. of F.E.A.R.* (GDC 2006)  
https://www.gamedevs.org/uploads/three-states-plan-ai-of-fear.pdf

Important takeaways:

- High level chooses **goal + action set**, not every transition.
- Local FSM/state logic still exists and executes.
- Shared working memory matters.
- Communication after the fact can narrate already-decided action, rather than drive it in real time.

**Adoptable pattern**

- Brain chooses:
  - which Expert
  - target / objective
  - risk policy
  - operating envelope
- Expert owns:
  - local state machine
  - scoring
  - micro / navigation / cooldown management
  - short-horizon retries

### 3.2 RTS planning research: hierarchy reduces branching factor

RTS planning research repeatedly uses hierarchy to reduce combinatorial branching. Ontañón and Buro’s AHTN work for RTS argues that real-time games need hierarchical decomposition because branching factors, simultaneity, durative actions, and limited decision time overwhelm flat search.  
Source: Ontañón and Buro, *Adversarial Hierarchical-Task Network Planning for Complex Real-Time Games* (IJCAI 2015)  
https://www.ijcai.org/Proceedings/15/Papers/236.pdf

**Adoptable pattern**

- Brain should reason in macro tasks and method choices.
- Experts should own primitive and durative execution.
- Multi-unit concurrent behavior should not be re-expanded into LLM token-level decisions.

### 3.3 Emerging LLM-game research still converges on planner/executor splits

Recent work like SC2Arena / StarEvolve still uses a hierarchical Planner-Executor-Verifier split for StarCraft II-style decision-making. That is notable because even when the whole system is LLM-centric, researchers still separate strategic planning from execution and self-correction.  
Source: Shen et al., *SC2Arena and StarEvolve* (arXiv, submitted August 14, 2025)  
https://arxiv.org/abs/2508.10428

This is emerging research, not production proof. But it reinforces the same conclusion: the right shape is not one flat language loop.

---

## 4. Concrete answers to the 5 design questions

### 4.1 How should Expert signals/events be structured for LLM consumption?

Use **typed, sparse, decision-oriented events**, not raw telemetry.

Recommended schema:

```json
{
  "event_id": "evt_204",
  "task_id": "task_001",
  "expert_id": "recon_001",
  "kind": "decision_request",
  "severity": "warning",
  "time": 1774760042.2,
  "summary": "Scout lost; no replacement available",
  "world_delta": {
    "lost_resources": ["actor:57"],
    "known_enemy_base": false,
    "new_enemy_contacts": []
  },
  "expert_state": {
    "phase": "searching",
    "resources": [],
    "progress_pct": 22,
    "local_confidence": 0.31
  },
  "decision": {
    "needed": true,
    "type": "strategy_choice",
    "deadline_s": 3.0,
    "options": [
      {"id": "wait_scout", "pros": ["preserve intent"], "cons": ["delay"]},
      {"id": "switch_to_infantry_recon", "pros": ["continue now"], "cons": ["higher loss risk"]},
      {"id": "abort_task", "pros": ["save resources"], "cons": ["objective unfinished"]}
    ],
    "default_if_timeout": "wait_scout"
  }
}
```

Rules:

- Include **what changed**, **why it matters**, **what the Expert is currently doing**, and **whether a decision is needed**.
- Prefer task-semantic event kinds:
  - `progress`
  - `risk_alert`
  - `target_found`
  - `resource_lost`
  - `blocked`
  - `decision_request`
  - `task_complete`
- Include compact expert self-assessment:
  - `phase`
  - `progress_pct`
  - `local_confidence`
  - `stuck_for_s`
  - `retry_count`

Do **not** send:

- per-tick positions
- every action
- low-level pathing noise
- repeated unchanged status

### 4.2 How should the framework inject game state context so the LLM does not need to query?

Use **push-based context packets** plus **event-triggered delta injection**.

Recommended Brain context packet:

```json
{
  "task": {
    "task_id": "task_001",
    "intent": "recon_find",
    "goal": "locate enemy base",
    "priority": 50
  },
  "expert": {
    "type": "ReconExpert",
    "phase": "searching_northeast",
    "resources": ["actor:57"],
    "config": {
      "search_region": "northeast",
      "avoid_heavy_aa": true,
      "retreat_hp_pct": 0.4
    }
  },
  "world_summary": {
    "economy": {"cash": 1800, "power": "normal"},
    "military": {"my_army_value": 2400, "enemy_army_value": 1800},
    "map": {"explored_pct": 0.45},
    "known_enemy": {"base_known": false, "recent_contacts": ["enemy_harvester@1700,350"]}
  },
  "recent_events": [
    "enemy_harvester_spotted heading southeast",
    "scout took minor damage but remains combat-capable"
  ],
  "open_decisions": []
}
```

Injection policy:

- At task start: full task packet
- On subscribed meaningful event: delta packet
- On brain wakeup after long silence: compressed summary packet
- On intervention: include last decision, current state, and options

This should be produced by the runtime, not the model.

### 4.3 What is the right granularity for Expert autonomy?

The Expert should own everything below the **semantic decision boundary**.

Expert decides locally:

- movement, pathing, targeting, stutter-step, regroup, local retries
- routine fallback inside current doctrine
- short-term adaptation to damage, threat, terrain, cooldowns
- use of already-approved tactics within a bounded envelope

Brain decides:

- task redefinition
- switching Expert type
- changing doctrine / policy / risk posture
- choosing among materially different strategic branches
- coordinating multiple Experts
- whether to continue after major failure / ambiguity

Escalate to Brain only when one of these is true:

1. Goal semantics changed
2. Multiple valid strategies have materially different opportunity cost
3. Local confidence drops below threshold for too long
4. Resource loss crosses an importance threshold
5. Another task / expert must be coordinated
6. Action would violate a user constraint or irreversible policy

### 4.4 How to handle the latency gap?

Use **asynchronous supervision with bounded autonomy**.

Mechanisms:

- Expert runs continuously at 100-1000 ms cadence.
- Brain is event-driven and wakes only on:
  - task start
  - decision request
  - major alert
  - completion
  - periodic coarse review
- Every Expert has a `default_if_timeout` policy.
- Brain decisions apply as:
  - config patch
  - target patch
  - constraint patch
  - pause / abort / replace

This is the key pattern from robotics: the fast controller never waits for the planner to keep the unit alive.

### 4.5 Fire-and-forget vs supervised tasks

This should be a first-class task attribute.

Recommended split:

**Fire-and-forget**

- routine
- reversible
- low coordination cost
- low strategic ambiguity
- easy to locally score

Examples:

- scout quadrant
- kite this skirmish within current rules
- continue producing assigned unit mix

Contract:

- Brain sets goal + envelope
- Expert executes autonomously
- Brain only gets milestone / exception events

**Supervised**

- irreversible or costly
- ambiguous tradeoffs
- cross-expert coordination required
- politically/user-sensitive
- high failure cost

Examples:

- commit main army attack
- sell base / move MCV
- tech switch
- all-in timing push

Contract:

- Brain receives richer updates
- Expert may require approval at explicit checkpoints
- runtime supports interrupt / resume / override

---

## 5. Recommended architecture for OpenRA

### 5.1 Control contract

Task Agent should control Experts through a narrow typed contract:

```python
class ExpertController(Protocol):
    def start(self, config: ExpertConfig) -> None: ...
    def patch(self, patch: ExpertPatch) -> None: ...
    def pause(self, reason: str) -> None: ...
    def resume(self) -> None: ...
    def abort(self, reason: str) -> Outcome: ...
```

Expert emits typed signals:

```python
class ExpertSignal(BaseModel):
    task_id: str
    expert_id: str
    kind: Literal[
        "progress", "risk_alert", "blocked",
        "decision_request", "resource_lost",
        "target_found", "task_complete"
    ]
    summary: str
    world_delta: dict
    expert_state: dict
    decision: dict | None
```

### 5.2 Runtime pattern

- `WorldModel` produces state snapshots + typed domain events
- `Kernel` routes them to subscribed Task Agents and Experts
- `Task Agent` owns one task-level blackboard / memory object
- `Expert` owns local working memory and control loop
- `Dashboard` consumes the same signal/event stream

### 5.3 Decision policy

Per Expert, define an autonomy policy:

```json
{
  "escalate_on": [
    "target_found",
    "resource_lost_major",
    "stuck_over_10s",
    "constraint_conflict",
    "strategy_branch_required"
  ],
  "default_on_timeout": "continue_current_policy",
  "review_interval_s": 8.0
}
```

This is more important than prompt wording. The runtime policy decides when the Brain is in the loop.

### 5.4 Memory / context budget

Do not keep a raw transcript as the main state.

Keep:

- latest task context packet
- last N important events
- compact decision history
- summarized expert status
- explicit open questions

Discard or summarize:

- per-tick traces
- repeated unchanged status
- full action logs unless in debug mode

---

## 6. Specific design recommendations for `design.md`

### Recommendation 1

Promote **Task Agent as supervisor**, not executor.

Suggested wording:

> Task Agent is an event-driven supervisory planner. It configures an autonomous Expert, subscribes to task-relevant signals, and intervenes only at semantic decision boundaries.

### Recommendation 2

Make **ExpertSignal** a first-class data model beside `Action` and `Outcome`.

This is currently the most important missing concept for the new architecture direction.

### Recommendation 3

Add **autonomy class** to `TaskSpec` or `ExecutionJob`:

- `autonomy_mode = fire_and_forget | supervised`

### Recommendation 4

Add a **context packet builder** in runtime:

- on task start
- on event escalation
- on coarse review tick

The Brain should consume runtime-built state packets, not perform ad hoc world queries as its main loop.

### Recommendation 5

Keep Expert control surface narrow:

- start
- patch
- pause
- resume
- abort

No generic “ask expert anything” loop on hot path.

### Recommendation 6

Define **escalation thresholds** per Expert type, not globally.

Examples:

- Recon escalates on ambiguity / scout loss / contact pattern change
- Combat escalates on force-ratio collapse / opportunity spike / target conflict
- Economy escalates on build deadlock / power crisis / tech-branch choice

---

## 7. Bottom line

The strongest cross-domain answer is:

- **Do not build a single flat LLM agent that continuously calls Experts like tools.**
- Build a **supervisory brain** over **autonomous experts**.
- Use **event-driven signals**, **runtime-injected context packets**, and **bounded autonomy envelopes**.
- Treat the LLM as a **slow strategic controller**, not a tactical loop.

The closest proven templates are:

1. **3T / hybrid robotics** for planner-vs-skill separation
2. **Nav2 BT navigator** for orchestrating modular executors with shared state
3. **F.E.A.R. GOAP** for high-level selection plus local execution logic
4. **AutoGen / CrewAI / LangGraph** for event-driven supervision, state injection, interrupts, and checkpointed long-running runs

If OpenRA follows those patterns, the design should converge toward a system where the Brain delegates, watches, and occasionally corrects, while the Cerebellum actually plays the game.
