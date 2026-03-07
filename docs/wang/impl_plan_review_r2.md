# Re-audit of `implementation_plan.md`

## Verdict

I clear the previous **5 planning gaps as closed**.

For the specific issues raised in the previous audit, my conclusion is:

1. `0.4` model abstraction dependency coverage: closed
2. benchmark integration into milestone tests and model evaluation: closed
3. timestamp propagation into LLM-facing context: closed
4. voice I/O dependency wiring: closed
5. critical path / milestone summary consistency: closed

I do **not** see any remaining blocker-level gap between the current `design.md` and `implementation_plan.md` on these points.

## What changed

### 1. Model abstraction is now wired into the model-using tasks

This was the largest previous planning gap.

Now `implementation_plan.md` explicitly threads `0.4` into the places that actually use models:

- `1.4` Task Agent agentic loop
- `4.1` Adjutant LLM
- `4.2` query LLM
- `5.7` voice I/O framework
- `7.2` model evaluation

That is aligned with design decision 25.

### 2. Benchmark is now integrated into the right checkpoints

Previously, the benchmark framework existed but was too detached from milestones and evaluation.

Now `0.5` is explicitly required by:

- `2.3` first end-to-end test
- `3.5` T2-T8 tests
- `4.5` T9-T11 tests
- `7.2` model evaluation
- `7.3` full end-to-end benchmark baseline

That is strong enough to satisfy the “full-pipeline benchmark” requirement in substance.

### 3. Timestamp propagation now explicitly covers LLM context

The prior issue was that the plan covered logs and outward payloads, but not clearly the LLM-facing context path.

Now the plan explicitly states:

- `1.4` context packet carries timestamp
- `1.7` includes `LLM context packet`
- `4.1` Adjutant context carries timestamp
- the cross-cutting constraints section also repeats the rule

That closes the previous timestamp/context gap.

### 4. Voice I/O dependency wiring is now coherent

Previously `5.7` only depended on the sidebar UI, which was architecturally wrong.

Now it depends on:

- `5.2` chat main view
- `0.4` model abstraction
- `4.1` Adjutant

That is a much better fit for the actual design.

### 5. Critical path and milestone summary are now refreshed

Previously, the summary section lagged behind the detailed table.

Now it has been updated to include:

- `0.4` / `0.5`
- `1.6-1.8`
- `4.5`
- refreshed milestone wording
- the new `跨切面约束` section

That resolves the previous summary/table mismatch.

## Cross-check against the design

The revised plan now lines up with the new design requirements:

- decision 23: timestamps everywhere, including LLM context
- decision 24: chat as the main frontend surface
- decision 25: model/framework separation everywhere
- decision 26: replaceable voice I/O / multimodal path
- decision 27: benchmark throughout the pipeline, not only at the end

On these points, I do not see a remaining contradiction between the two documents.

## Residual nits

I only see minor non-blocking nits:

- the technology table still names `Qwen3.5（暂定）` even though the architecture now emphasizes swappable models; that is acceptable as a default, not a contradiction
- the critical path still compresses some branches for readability rather than showing every dependency edge explicitly; that is also acceptable

## Bottom line

For the 5 issues from the previous deep audit:

- **all 5 are now closed**
- **zero gaps remain at blocker level**

This revision is consistent enough to proceed.
