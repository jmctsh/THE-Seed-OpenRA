# Pending Drift Fixes

These are confirmed implementation drifts or test-discovered gaps that should be fixed after the current live test round is closed.

## 1. Task-to-player dialogue drift

- `design.md` expects Task-side interaction to reach the player through Adjutant using structured messages such as `task_info`, `task_warning`, `task_question`, and `task_complete_report`.
- Current `TaskAgent` has no direct tool for this. It can only:
  - execute job/control tools,
  - `complete_task(...)`,
  - rely on indirect `TaskMessage`/`player_notification` paths.
- Result:
  - task execution is largely silent in the main chat,
  - players cannot easily tell what a managed task is doing mid-flight,
  - the implementation has drifted from the interaction model in `design.md`.

Pending fix direction:
- Add an explicit TaskAgent tool for structured task messaging through Kernel/Adjutant, instead of relying on incidental notifications.

## 2. Composite-task phase policy drift

- Multi-step natural-language tasks like `发展一下科技，然后探索地图` or `整点步兵，探索一下地图` still allow too much free-form LLM planning.
- Current system does not enforce a stable phase policy such as:
  - phase A: satisfy infrastructure/economy prerequisites,
  - phase B: produce requested units,
  - phase C: start recon.
- Result:
  - LLM can pivot across unrelated Experts,
  - tasks drift into low-value retries or strategy jumps,
  - user intent is not preserved tightly enough.

Pending fix direction:
- Introduce bounded phase templates for composite commands so the LLM consumes expert outputs within a controlled workflow instead of improvising the whole doctrine.

## 3. Runtime log durability gap

- Current structured logs are primarily process-memory history.
- `Diagnostics` replay now works for the current backend process, but logs are still not durable across backend restarts.
- Result:
  - a task can be analyzed live,
  - but once the backend restarts, its detailed trace is lost unless separately exported.

Pending fix direction:
- Persist structured runtime logs or task traces to a rolling on-disk store for postmortem debugging across restarts.
- Once runtime logs/trace become durable, define whether `session_clear` should also prune persisted records for the current game session, or only reset in-memory state.

Additional notes from live investigation:
- The Python/GameAPI/OpenCodeAlert code path does pass `autoPlaceBuilding=True` for building jobs; this is not a simple “flag never sent” bug.
- The more likely failure class is workflow/state handling around the shared player build queue: aborted jobs can leave queued or ready items behind, and no singleton runtime manager currently cleans or escalates them.

## 4. Case study: Task003 composite-command drift

- User-facing task: `Task003`
- Real backend task:
  - `task_id = t_f6342c89`
  - `raw_text = 整点步兵，探索一下地图`
- Final status: `failed`

Observed job chain:
- `j_0405f2ef` — `EconomyExpert` — `Infantry · inf × 3` — `aborted`
- `j_0409f0ce` — `EconomyExpert` — `Building · proc × 1` — `aborted`
- `j_5be99089` — `ReconExpert` — `enemy_half / base` — `aborted`
- `j_78c85d01` — `EconomyExpert` — `Building · barr × 1` — `succeeded`
- `j_9a22c0a8` — `ReconExpert` — `full_map / base` — `aborted`
- `j_adc616bb` — `EconomyExpert` — `Vehicle · jeep × 1` — `aborted`
- `j_d8a8ff37` — `EconomyExpert` — `Building · warf × 1` — `aborted`

Preliminary diagnosis:
- This command bypassed the simple deterministic rule route because it is a composite command, not a simple single-intent build/produce/recon phrase.
- Once it entered the managed TaskAgent path, the task had no bounded phase policy like:
  - phase A: satisfy infantry prerequisites
  - phase B: produce infantry
  - phase C: start recon
- The result was cross-domain drift:
  - infantry production attempt,
  - refinery attempt,
  - recon attempt,
  - barracks build,
  - deeper recon,
  - jeep attempt,
  - war factory attempt.
- This is not a single-expert failure. It is a planning-layer control failure caused by letting the LLM improvise a multi-step RTS workflow without a stable composite-task template.

Why the user perceived “it keeps building barracks”:
- The task visibly succeeded in creating at least one `barracks` job (`j_78c85d01`) while the rest of the task continued drifting through other retries.
- From the user perspective, the task did not converge on the requested outcome (`整步兵 + 探图`), so the visible structure build looked like repeated meaningless work.

Pending fix direction:
- Add composite-task templates for command families like:
  - `produce_units_then_recon`
  - `tech_up_then_recon`
- Bound allowed experts per phase and require a clear transition condition before the next phase can begin.

## 5. Shared build-queue cleanup and queue manager gap

- `EconomyJob` currently controls production queue work, but shared player queues outlive individual jobs.
- If a managed task drifts and aborts/replans, queued production items can remain in the shared queue after the original job is gone.
- The current system has no singleton queue manager to:
  - watch for ready buildings stuck at the top of the shared queue,
  - auto-place them after a timeout,
  - or switch to warn-only / off mode.

Desired direction:
- Add a singleton runtime `QueueManager` (not a per-task job) with modes:
  - `off`
  - `warn`
  - `auto_place`
- Default policy under discussion:
  - if a ready building stays stuck for more than 5s, either auto-place it or emit a warning depending on mode
- This manager should also emit explicit observability events / notifications such as:
  - `queue_ready_stuck`
  - `queue_auto_placed`
  - `queue_auto_place_failed`

## 6. EconomyJob abort cleanup gap

- `Kernel.abort_job()` changes Job state and releases resources, but does not clean shared production queue state.
- For `EconomyJob`, aborting after production has already been queued can leave stray items behind.

Desired direction:
- `EconomyJob.abort()` should attempt best-effort queue cleanup when the front of the matching queue still belongs to the same production intent.
- Because the queue is shared and item provenance is not yet explicit, this cleanup can only be best-effort for now.
