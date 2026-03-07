# Deep audit of `design.md` + `implementation_plan.md`

## Verdict

The 5 new requirements are integrated into `design.md` in a coherent way, but `implementation_plan.md` still has **5 concrete gaps / inconsistencies**.

So my answer to the audit checklist is:

1. `design.md` decisions 23-27 are **mostly internally consistent**
2. `implementation_plan.md` covers **most**, but **not all**, of those requirements
3. some dependencies are still wrong or incomplete
4. the model abstraction layer is **not yet referenced everywhere it must be**
5. the benchmark framework exists in the plan, but its integration point is still too weak/late
6. there are still contradictions between the detailed task table and the plan summary / milestones

## Findings

### 1. The model abstraction layer is not actually wired into every model-using task

`design.md` decision 25 says:

- all model-using places must have model/framework separation
- models should be swappable in one line

([design.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/design.md#L502))

`implementation_plan.md` adds:

- `0.4 | LLM 模型抽象层`

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L28))

But the plan does **not** thread `0.4` into the later tasks that use models:

- `1.4 Task Agent agentic loop` depends only on `0.2`
- `4.1 Adjutant LLM` depends on `1.3, 1.4`
- `4.2 查询 LLM` depends only on `1.1`
- `5.7 语音输入/输出框架` has no dependency on model abstraction
- `7.2 LLM 模型实测` depends only on `1.4`

This means the plan says “model abstraction everywhere”, but the dependency graph still treats most model-using work as if `0.4` were optional.

### 2. The benchmark framework is defined, but integrated too late and too weakly

`design.md` decision 27 says:

- full-pipeline log + benchmark
- every step timed
- queryable for optimization

([design.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/design.md#L506))

`implementation_plan.md` adds:

- `0.5 Benchmark 框架`
- `6.1-6.3` benchmark/log integration and query tools

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L29))

That is a good addition, but it is still too late in the plan for a requirement phrased as “every step timed”.

Problems:

- `2.3`, `3.5`, and `4.5` milestone-grade end-to-end tests can all happen before benchmark instrumentation is actually integrated
- `7.2 LLM 模型实测` does not depend on the benchmark/query tooling that should be used to compare models

If Wang wants benchmarking to drive optimization rather than be added after the fact, some instrumentation must move earlier or become an explicit dependency for the model-eval path.

### 3. The new timestamp requirement is only partially mapped into implementation tasks

`design.md` decision 23 is stronger than the earlier frontend-only version:

- timestamps on **all information**
- explicitly including **LLM context**
- context packets, `ExpertSignal`, and `Event` should all carry time

([design.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/design.md#L470))

`implementation_plan.md` partially reflects this through:

- `0.2` all models carry timestamp
- `1.7` all outward payloads carry timestamp
- `6.1` logs have timestamp

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L26))

What is still missing is an explicit task for timestamping **LLM-facing context builders**, especially:

- Task Agent context packet builder (`1.4`)
- Adjutant query context / chat context (`4.1`, `4.2`)
- any voice-to-text / text-to-voice interaction payloads (`5.7`)

So the plan now covers model structs and player-facing payloads, but it still does not explicitly map the “timestamps inside LLM context” part of the design.

### 4. Voice I/O dependency wiring is wrong

`design.md` decision 26 says:

- support ASR + TTS basic framework
- or replace with multimodal model
- still under model/framework separation

([design.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/design.md#L474))

`implementation_plan.md` adds:

- `5.7 语音输入/输出基础框架（ASR→文本→Adjutant / Adjutant→文本→TTS，模型可替换）`

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L91))

But `5.7` currently depends only on:

- `5.3` Task sidebar

That dependency does not match the actual architecture.

Voice I/O should depend much more directly on:

- `4.1` Adjutant
- `4.2` query path
- `5.2` chat main view
- `0.4` model abstraction
- likely `1.6` backend WebSocket/server plumbing

So the task exists, but its dependency placement is wrong.

### 5. The plan summary, key path, and milestones are stale relative to the detailed task table

The detailed task table was updated with:

- `0.4`, `0.5`
- `1.6`, `1.7`, `1.8`
- `4.5`
- `5.7`

But the summary/critical-path section still says:

- `0.1-0.3 → ...`
- omits `0.4`, `0.5`, `1.6-1.8`, `4.5`, `5.7`
- milestone 3 still says `4.4 — 玩家交互完整`

([implementation_plan.md](/Users/kamico/work/theseed/THE-Seed-OpenRA/docs/wang/implementation_plan.md#L110))

That is now inconsistent with the detailed plan:

- `4.4` is only Adjutant routing tests
- `4.5` is the actual T9-T11 end-to-end interaction checkpoint
- voice support `5.7` is omitted from the path entirely despite being a new stated requirement

This is not just cosmetic. The summary is now giving a different sequencing story from the table.

## What is already good

To be clear, the update did fix several of the earlier planning gaps:

- backend WS task now exists (`1.6`)
- global timestamp propagation now exists (`1.7`)
- explicit `review_interval` scheduler task now exists (`1.8`)
- Adjutant routing tests now exist (`4.4`)
- chat is correctly moved to the main frontend view (`5.2`)
- benchmark framework now exists as a named work item (`0.5`)

So this is not a failed revision. It is a strong revision with a few remaining integration mistakes.

## Bottom line

The new design requirements are mostly coherent and mostly reflected in the plan.

The remaining issues are concentrated in 3 areas:

1. `0.4` model abstraction must become a real dependency of every model-using task
2. benchmark/timestamp requirements still need stronger integration into the early runtime and eval path
3. the plan summary / milestones must be updated to match the detailed task table

## Shortest fix set

1. Add `0.4` as a dependency for:
   - `1.4`
   - `4.1`
   - `4.2`
   - `5.7`
   - `7.2`
2. Add explicit timestamp/context work to:
   - `1.4` Task Agent context packet builder
   - `4.1/4.2` Adjutant/query context builders
   - `5.7` voice payload path
3. Pull benchmark instrumentation earlier or make it a dependency of model evaluation and milestone tests
4. Fix `5.7` dependencies
5. Refresh the critical path and milestone labels to match the table
