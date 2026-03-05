# Round 6 scenario audit of `design.md`

## Verdict

**A-H now have zero hard blockers on their mainline paths.**

Round 6 closes H in substance:

- bare natural-language constraint commands now have an explicit default scope rule
- `别追太远` is no longer ambiguous in a multi-task environment
- the runtime interaction with concurrent tasks is now clear enough to implement

The new remaining blocker class is concentrated in **Scenario I**. I found **1 hard blocker** there.

Current status:

- **A. 生产5辆重型坦克**: zero hard blockers
- **B. 所有部队撤退回基地**: zero hard blockers
- **C. 别追太远**: zero hard blockers
- **D. 包围右边那个基地**: zero hard blockers
- **E. 修理我的坦克，然后继续进攻**: zero hard blockers
- **F. 敌人在攻击我的基地！**: zero hard blockers
- **G. 建造一个新基地在右边矿区**: zero hard blockers
- **H. 连续快速下达 3 条命令**: zero hard blockers
- **I. 玩家长时间不下命令，但局势出现战略机会**: 1 blocker remains

## What changed since Round 5

The previous H blocker is now explicitly closed by the new rule:

- bare player-issued constraint commands default to `scope=global`
- they affect all current and future matching Jobs unless the Task Agent intentionally narrows scope

That is sufficient to make the H concurrency case implementable.

## Scenario H: rapid sequence of 3 player commands

Player inputs in quick succession:

1. “生产坦克”
2. “探索地图”
3. “别追太远”

### Mainline trace

1. Kernel receives command 1 and creates Task H1 (`background`).
2. Task Agent H1 starts EconomyJob.
3. Kernel receives command 2 and creates Task H2 (`managed`).
4. Task Agent H2 starts ReconJob.
5. Kernel receives command 3 and creates Task H3 (`constraint`).
6. Task Agent H3 creates `do_not_chase` constraint.
7. Because the spec now states that bare constraint commands default to `scope=global`, the constraint applies to all current and future matching CombatJobs.
8. EconomyJob is unaffected.
9. ReconJob is unaffected unless later combat follow-up jobs are spawned.
10. Kernel continues concurrent scheduling and resource arbitration as already specified.

### Blocker status

**No hard blocker found.**

## Scenario I: no new player commands, but the game state creates a strategic opportunity

Scenario:

- the player says nothing for a long time
- economy is growing
- scouting discovers the enemy is expanding
- our frontline is empty

The question is whether the system should proactively do anything, and if so, how that happens in the current architecture.

### Intended capability

For this scenario to be implementation-ready, the spec needs to clearly answer all of the following:

1. Is there any standing background Task or always-on policy layer that keeps evaluating economy / scouting / defense posture even when the player gives no new command?
2. Can Kernel auto-create Tasks for strategic opportunities, not just emergencies?
3. If yes, what authority boundary applies:
   - auto-create a production task?
   - auto-create a defense posture task?
   - auto-create a harassment / expansion-response task?
   - only emit a recommendation to the player?

### What is clear from the current spec

- The system is fundamentally driven by:
  - player-created Tasks
  - Job-originated `ExpertSignal`
  - a very small set of Kernel passive event rules
- Kernel passive auto-response is explicitly specified for:
  - `BASE_UNDER_ATTACK`
- Background Tasks exist as a task kind, but only as a result of a player command such as “生产5辆坦克”.
- Jobs are autonomous once started, but the spec does not define a standing “strategic manager” Task that is always alive without player instruction.

### Remaining blocker

**1 hard blocker remains:** the spec still does not define the proactive-autonomy model for no-command strategic opportunity handling.

Concretely, the architecture is missing an explicit answer to this branch:

1. No player command arrives.
2. World state changes suggest a strategic opportunity or strategic risk:
   - economy is improving
   - enemy expansion is detected
   - frontline posture is weak
3. What happens next?

Right now the spec does not say whether:

- nothing should happen unless the player asks
- an existing background Task should notice and act
- Kernel should auto-create a new managed/background Task from a non-emergency rule
- the system should escalate to the player as a recommendation instead of acting directly

Why this is a real implementation blocker:

- Without this policy, the implementer cannot decide whether the system is:
  - purely reactive to commands plus emergencies
  - or strategically proactive within bounded authority
- The required runtime ownership is also unclear:
  - if proactive behavior belongs to Kernel, it needs a new class of pre-registered strategic rules
  - if it belongs to a standing Task Agent, the spec must define who creates it, its lifetime, and its authority
  - if it belongs to existing Jobs, the current Job contracts are too local and too expert-specific to own cross-domain strategic decisions

### Shortest way to close I

Add one explicit architecture rule for **no-command proactive behavior**. For example:

- either: “The system never creates strategic Tasks without player input; only emergencies like `BASE_UNDER_ATTACK` are auto-created.”
- or: “Kernel may auto-create bounded strategic Tasks from a pre-registered opportunity/risk rule set.”
- or: “A standing background StrategyTask continuously evaluates world state and may create subordinate Tasks within a fixed authority budget.”

Any of those can work. The blocker is not which choice Wang makes. The blocker is that the current spec does not choose one.

## Bottom line

Round 6 closes the previous H blocker in substance:

- **A-H now have zero hard blockers on their mainline paths**

The remaining unresolved area is system behavior when the player says nothing but the game presents a strategic opportunity:

1. declare whether the architecture is command-reactive only, or proactively strategic within bounded authority
2. if proactive behavior is allowed, assign ownership explicitly: Kernel rule layer vs standing background Task vs recommendation-only path
