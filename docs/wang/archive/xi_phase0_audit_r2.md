# xi Phase 0 Audit R2

Scope re-audited after xi commit `1f5a7ce`:
- `models/configs.py`
- `models/__init__.py`
- `llm/provider.py`

Reference decision from Wang:
- Fix required: config binding
- Fix required: enum-typed config fields
- Deferred to Phase 1: full Anthropic multi-turn tool-use transcript conversion, but limitation must be documented

## Result

Zero blockers for the requested Phase 0 follow-up fixes.

## What Changed Correctly

### 1. Config binding is now explicit
- `models/configs.py` now defines `EXPERT_CONFIG_REGISTRY`
- `models/configs.py` now defines `validate_job_config(expert_type, config)`
- The helper rejects mismatched config classes and unknown expert types

I verified locally:
- `validate_job_config("CombatExpert", CombatJobConfig(...))` succeeds
- `validate_job_config("MovementExpert", MovementJobConfig(...))` succeeds
- `validate_job_config("CombatExpert", ReconJobConfig(...))` raises `TypeError`

This closes the prior blocker that `expert_type` and `config` were only descriptively related.

### 2. Closed-vocabulary config fields now use enums
- `CombatJobConfig.engagement_mode` now uses `EngagementMode`
- `MovementJobConfig.move_mode` now uses `MoveMode`

I verified locally that these dataclasses instantiate with enum values and preserve enum types at runtime.

This closes the prior “stringly typed schema” issue for the fields I flagged.

### 3. Anthropic limitation is now documented
- `llm/provider.py` docstring now explicitly states that multi-turn tool-use transcript conversion is not yet implemented
- The limitation is correctly framed as deferred Phase 1 work rather than silently pretending provider parity already exists

This matches Wang’s Phase 0 decision.

## Residual Notes

- I still do not see automated tests added specifically for `validate_job_config()`, but the behavior is small and my local inline regression covered the intended positive/negative cases.
- `models/configs.py` still imports `field` without using it. This is only a cleanup nit.

## Verdict

For the Phase 0 follow-up items, I clear xi’s fixes as `zero blockers`.
