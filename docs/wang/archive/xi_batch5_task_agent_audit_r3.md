# Final Regression Audit — xi player-warning callback fix (`9882e5c`)

## Scope

- `task_agent/agent.py`
- `task_agent/__init__.py`
- `tests/test_task_agent.py`
- live integration repro against `kernel/core.py`

## Verdict

Still not `zero blockers`.

## Findings

### Blocker 1 — default Kernel integration still does not pass the new `message_callback`, so live warning delivery remains broken

Files:
- `task_agent/agent.py:78-95`
- `task_agent/agent.py:349-374`
- `kernel/core.py:527-543`

The Task Agent side is now correct in isolation:

- `TaskAgent` accepts `message_callback`
- `_notify_player_llm_failure()` builds `TaskMessage(type=task_warning, ...)`
- it calls the callback instead of pushing an internal signal

But the default live wiring is still missing. `Kernel._default_task_agent_factory()` still constructs:

- `TaskAgent(..., config=self.config.default_agent_config)`

and does **not** pass:

- `message_callback=self.register_task_message`

So the new outbound path is never connected in the real runtime.

This is exactly what Wang asked me to verify with the live repro, and it still fails:

- always-failing LLM
- `Kernel.create_task(...)`
- wait for auto-fail path
- `kernel.list_task_messages(task_id)` is still empty

So the implementation now has the right callback hook, but the actual Kernel integration did not pick it up.

### Should-fix 1 — the new unit test validates only injected callback usage, not the real Kernel assembly path

Files:
- `tests/test_task_agent.py:498-554`

The updated test uses:

- `message_callback=capture_message`

which proves the Task Agent can emit a `TaskMessage` when manually wired. That is useful, but it does not test the default production path Wang explicitly asked to verify:

- `Kernel -> create_task -> default TaskAgent factory -> task warning reaches Kernel`

This is why the suite passes while the live repro still fails.

## Verification

- `python3 tests/test_task_agent.py` -> `16 passed`
- `python3 -m py_compile task_agent/agent.py tests/test_task_agent.py task_agent/__init__.py`
- Live repro: `Kernel + WorldModel + always-failing LLM`
  - final task status: `failed`
  - `kernel.list_task_messages(task_id)` -> `[]`
  - `kernel.player_notifications` -> `[]`

## Conclusion

This fix closes the Task Agent's local API shape, but not the actual runtime integration. The last remaining blocker is simple and mechanical: the default Kernel TaskAgent factory still needs to pass `message_callback=self.register_task_message`. Until that wiring exists, the repeated-failure `task_warning` does not reach Kernel in the live system.
