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
