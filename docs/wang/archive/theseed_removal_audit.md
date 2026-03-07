# Audit before removing the `the-seed` submodule

## Short answer

**Most of `the-seed` can be removed.**

For the new architecture, I do **not** see any major runtime/framework component in `the-seed` that should be preserved as-is.

Before deletion, the only things that still need attention are:

1. **NLU rule assets still referenced by `nlu_pipeline/` scripts**
2. **a few old runtime / gateway imports in the main project that must be deleted or replaced first**

`OpenCodeAlert/` is unrelated and should be kept.

## What `the-seed/` contains

At a high level the submodule contains:

- `the_seed/config/`
  - config schema / config loader / command dict
- `the_seed/core/`
  - new simplified executor stack: `CodeGenNode`, `SimpleExecutor`, `ExecutionResult`
  - routed executor
  - legacy FSM / node framework under `core/legacy/`
- `the_seed/demos/openra/`
  - OpenRA-specific rule router
  - command dictionary
  - command templates
- `the_seed/model/`
  - model adapter / provider wrapper
- `the_seed/utils/`
  - logging
  - dashboard bridge
  - prompt builder
- packaging metadata

In other words, it is mostly:

- old execution framework
- old OpenRA command-routing/templates
- old config/model/logging helpers

## Cross-reference against the new architecture

### Safe to remove with the submodule

These are clearly superseded by the rewrite:

- `SimpleExecutor` / `CodeGenNode`
  - replaced by Task Agent + Experts
- `core/legacy/` FSM / node system
  - replaced by Kernel + Task Agent + Job runtime
- config schema / config manager / model adapter
  - replaced by the new local models/runtime choices
- `command_router` for runtime command handling
  - replaced by Adjutant + Task Agent architecture
- `DashboardBridge` / `LogManager` / prompt helpers
  - replaced by new dashboard + structured logging + new agent loop
- OpenRA command templates
  - tied to the old template-codegen path, not the new design

### Not in `the-seed`, so not a blocker for submodule removal

Wang's guess is correct here:

- NLU model artifacts / training outputs live in `nlu_pipeline/`, not in `the-seed`
- the new architecture documents and plans live outside the submodule

## What is still needed before deletion

### 1. NLU weak-label / data-collection scripts still depend on `the-seed` rules

This is the only part that looks worth copying or rewriting before submodule removal.

Current dependencies:

- `nlu_pipeline/scripts/rule_weak_labeler.py`
  - imports `the_seed.demos.openra.rules.command_router.CommandRouter`
- `nlu_pipeline/scripts/build_annotation_queue.py`
  - imports `the_seed.demos.openra.rules.command_router.CommandRouter`
- `nlu_pipeline/scripts/collect_online_batch.py`
  - imports `COMMAND_DICT`, `ENTITY_ALIASES`, `FACTION_ALIASES`

Important nuance:

- if you want to keep `CommandRouter` behavior as-is, copying only `command_router.py` is **not enough**
- it also depends on:
  - `command_dict.py`
  - command templates under `the_seed/demos/openra/templates/commands/`
  - `the_seed.utils.LogManager`

So the better move is probably **not** “copy half the submodule”.

Recommended approach:

- extract a **small local rule package** for `nlu_pipeline` only
- keep only:
  - intent/alias dictionaries
  - minimal rule matcher needed for weak labeling / annotation queue generation
- do **not** carry over the template-rendering executor-oriented parts unless they are still actively needed

### 2. Some old runtime code in the main project still imports `the-seed`

These imports do not mean the submodule is strategically needed.
They mean removal will break old entrypoints unless they are deleted or rewritten first.

## Current imports from the main project

### Runtime / main code

- `main.py`
  - `the_seed.core.factory.NodeFactory`
  - `the_seed.core.fsm.FSM`, `FSMContext`, `FSMState`
  - `the_seed.utils.LogManager`, `build_def_style_prompt`
- `main_legacy.py`
  - same legacy stack plus `DashboardBridge`, `hook_fsm_transition`
- `adapter/openra_env.py`
  - `the_seed.utils.LogManager`
- `agents/nlu_gateway.py`
  - `the_seed.core.ExecutionResult`, `SimpleExecutor`
  - `the_seed.demos.openra.rules.command_router.CommandRouter`
  - `the_seed.utils.DashboardBridge`, `LogManager`

### NLU / data scripts

- `nlu_pipeline/scripts/rule_weak_labeler.py`
  - `the_seed.demos.openra.rules.command_router.CommandRouter`
- `nlu_pipeline/scripts/build_annotation_queue.py`
  - `the_seed.demos.openra.rules.command_router.CommandRouter`
- `nlu_pipeline/scripts/collect_online_batch.py`
  - `the_seed.demos.openra.rules.command_dict.COMMAND_DICT`
  - `ENTITY_ALIASES`, `FACTION_ALIASES`
- `nlu_pipeline/scripts/p0_p1_regression_test.py`
  - `the_seed.core.ExecutionResult`
- `nlu_pipeline/scripts/runtime_runtest.py`
  - `the_seed.core.ExecutionResult`
- `nlu_pipeline/scripts/smoke_runtime_gateway.py`
  - `the_seed.core.ExecutionResult`

### Tests / shell scripts

- `test_simple.py`
  - imports executor/model/config/utils from `the_seed`
- `test_legacy.py`
  - imports legacy FSM stack
- `test_backend.sh`
  - imports config / factory / FSM / DashboardBridge

### Type-only reference

- `agents/enemy_agent.py`
  - `TYPE_CHECKING` imports from `the_seed`
  - not a runtime dependency, but should still be cleaned up

## What should be copied out before deletion

If the goal is minimum preservation before deleting `the-seed`, I would only consider copying out:

1. **NLU rule dictionaries / aliases**
   - from `the_seed/demos/openra/rules/command_dict.py`
2. **A slimmed-down local rule matcher for `nlu_pipeline`**
   - based on `command_router.py`
   - but stripped of executor/template dependencies if possible
3. **Possibly a tiny local `ExecutionResult` compatibility type**
   - only if you want existing `nlu_pipeline` regression/smoke scripts to keep running unchanged during the transition

I would **not** copy out:

- `SimpleExecutor`
- `CodeGenNode`
- legacy FSM / node system
- config manager / schema
- model adapter
- dashboard bridge
- prompt builder

## Recommended removal sequence

1. Move or rewrite `nlu_pipeline`'s dependence on:
   - `CommandRouter`
   - `COMMAND_DICT` / aliases
2. Decide whether to keep old gateway/regression scripts alive temporarily:
   - if yes, replace their `ExecutionResult` dependency locally
   - if no, delete/update them together with the old runtime
3. Delete or replace old runtime entrypoints that still import `the-seed`:
   - `main.py`
   - `main_legacy.py`
   - `agents/nlu_gateway.py`
   - `adapter/openra_env.py`
4. Remove the `the-seed` submodule

## Bottom line

For the rewritten architecture, **nothing in `the-seed` looks worth preserving as a framework**.

Before removal, the only clearly valuable content is:

- a **small subset of OpenRA NLU rule assets** still used by `nlu_pipeline`

Everything else is either:

- already replaced in the new design
- old runtime glue that should be deleted
- or test/legacy compatibility code that can be dropped or trivially replaced
