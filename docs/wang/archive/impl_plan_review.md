# Audit of `design.md` updates + `implementation_plan.md`

## Verdict

The updated `design.md` direction is still coherent, but the new `implementation_plan.md` does **not yet fully cover** the revised design surface.

I found **4 implementation-planning gaps**:

1. missing backend WebSocket / message-gateway work
2. missing Adjutant-specific routing tests
3. `Task Agent` scheduling ownership is not cleanly mapped after adding `review_interval`
4. the new global `timestamp` requirement is not mapped to concrete implementation tasks

These are planning/coverage problems, not a return of the earlier architecture contradictions.

## Findings

### 1. The plan has frontend WebSocket work, but no backend transport/message-gateway tasks

`design.md` now relies on an explicit interaction boundary:

- WebSocket inbound: `command_submit`, `command_cancel`, `mode_switch`
- WebSocket outbound: `world_snapshot`, `task_update`, `task_list`, `log_entry`, `player_notification`, `query_response`

([design.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/design.md#L467))

But `implementation_plan.md` only schedules:

- frontend WebSocket connection in 5.1
- frontend panels in 5.2-5.5

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L65))

What is missing is the server-side transport layer:

- WebSocket server / connection manager
- inbound command handlers
- outbound payload serializers / broadcasters
- Adjutant/Kernel/Dashboard message bridge

Right now the plan assumes WebSocket exists as infrastructure, but no task actually implements it.

### 2. The plan does not include tests for the new Adjutant routing behavior

`design.md` §6 now defines critical interaction behavior beyond T9-T11:

- reply routing back to a waiting Task
- new command during a pending question
- simultaneous pending questions
- timeout fallback and late-reply policy

([design.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/design.md#L400))

But `implementation_plan.md` only schedules:

- `4.4 | 端到端测试 T9-T11（并发、空闲、查询）`

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L60))

And the current `test_scenarios.md` does not cover the new Adjutant dialogue-routing scenarios at all.

That means the most recently added interaction layer has no explicit validation task in the implementation plan.

### 3. `review_interval` and periodic Task-Agent wake scheduling are not cleanly owned in the plan

`design.md` changed the runtime model materially:

- Task Agent is now `事件驱动 + 定时轮询`
- each Task has `review_interval`
- wake reasons are now `Signal / Event / 定时`
- wake then enters a multi-turn tool-use loop

([design.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/design.md#L275))

But in `implementation_plan.md`:

- 1.2 GameLoop includes `check timeouts`
- 1.3 Kernel includes `pending question timeout`
- 1.4 Task Agent includes `review_interval + event queue + context packet builder`

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L32))

The ownership boundary is not fully clean:

- who schedules the periodic `review_interval` wakeups
- where the wake queue lives
- whether GameLoop, Kernel, or TaskAgent owns the timer registration

This matters because the plan claims tasks are dependency-ordered, but 1.4 currently depends only on `0.2`, even though the review mechanism clearly interacts with WorldModel/Kernel/GameLoop runtime scheduling.

I would at minimum either:

- move explicit periodic-wake scheduling into Kernel/GameLoop tasks
- or add a dedicated scheduler task and make 1.4 depend on it

### 4. The new global `timestamp` requirement is not translated into concrete implementation work

`design.md` now says:

- all outward-facing information must carry `timestamp`
- this includes task state, signals, notifications, logs, chat messages

([design.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/design.md#L470))

But in `implementation_plan.md`, the only explicit timestamp-focused item is:

- `6.1 | 日志框架（... timestamp）`

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L76))

And frontend relative-time display is implied in 5.2, but there is no task for:

- adding timestamps to WebSocket payload schemas
- stamping `player_notification` / `query_response`
- stamping Adjutant chat messages / task questions
- ensuring task updates and dashboard DTOs all carry consistent event times

So the plan currently covers timestamping for logs, but not for the broader user-visible contract that the design now requires.

## Secondary notes

### Milestone wording is slightly misleading

`implementation_plan.md` says:

- `第二个里程碑：3.5 — 四种 Expert 都能工作`

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L107))

But by that point the system has:

- Recon
- Economy
- Movement
- Combat
- Deploy

So the wording is a minor nit, not a blocker.

### The design updates themselves are directionally reasonable

I do not object to the `design.md` changes themselves:

- `review_interval` is a sensible addition for long-running Tasks
- multi-turn tool use is consistent with the current Task-Agent direction
- the timestamp requirement improves UX/debuggability

The problem is that the implementation plan has not yet fully absorbed those additions.

## Bottom line

`design.md` is ahead of `implementation_plan.md` right now.

The shortest path to fix that is:

1. add a backend WebSocket / message-bus implementation task
2. add explicit Adjutant routing tests
3. assign ownership for `review_interval` wake scheduling
4. add timestamp propagation tasks for all outward-facing payloads, not just logs
