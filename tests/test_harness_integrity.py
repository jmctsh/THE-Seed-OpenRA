"""Meta-tests that keep the runtime test harness honest."""

from __future__ import annotations

from pathlib import Path


def test_runtime_e2e_files_are_explicitly_layered() -> None:
    root = Path(__file__).resolve().parent
    expected_markers = {
        "test_e2e_adjutant.py": "mock_integration",
        "test_e2e_capability_bootstrap.py": "mock_integration",
        "test_e2e_experts.py": "mock_integration",
        "test_e2e_full.py": "mock_integration",
        "test_e2e_t1.py": "mock_integration",
        "test_live_e2e.py": "live",
    }

    for filename, marker in expected_markers.items():
        text = (root / filename).read_text(encoding="utf-8")
        assert f"pytestmark = pytest.mark.{marker}" in text, filename


def test_pytest_ini_declares_runtime_test_layers() -> None:
    root = Path(__file__).resolve().parent.parent
    text = (root / "pytest.ini").read_text(encoding="utf-8")
    for marker in ("startup_smoke", "contract", "runtime_invariants", "mock_integration", "live"):
        assert f"{marker}:" in text, marker


def test_regular_test_files_delegate_main_runner_to_pytest() -> None:
    root = Path(__file__).resolve().parent
    delegated_files = [
        "test_adjutant.py",
        "test_adjutant_coordinator.py",
        "test_demo_capability_truth.py",
        "test_economy_expert.py",
        "test_game_api.py",
        "test_game_control.py",
        "test_game_loop.py",
        "test_kernel.py",
        "test_logging_system.py",
        "test_planners.py",
        "test_task_agent.py",
        "test_tool_handlers.py",
        "test_unit_request.py",
        "test_world_model.py",
        "test_ws_and_review.py",
    ]
    expected = 'raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))'
    for filename in delegated_files:
        text = (root / filename).read_text(encoding="utf-8")
        assert expected in text, filename
