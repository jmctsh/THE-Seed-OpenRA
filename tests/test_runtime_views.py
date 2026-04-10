from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime_views import CapabilityStatusSnapshot
from task_triage import capability_blocker_status_text


def test_capability_snapshot_normalizes_alias_fields() -> None:
    snapshot = CapabilityStatusSnapshot.from_mapping(
        {
            "taskId": "cap-1",
            "label": "001",
            "phase": "dispatch",
            "blocker": "pending_requests_waiting_dispatch",
            "dispatch_request_count": "2",
            "recent_directives": ["发展经济", None, " 优先补电 "],
        }
    )

    assert snapshot.task_id == "cap-1"
    assert snapshot.task_label == "001"
    assert snapshot.phase == "dispatch"
    assert snapshot.dispatch_request_count == 2
    assert snapshot.recent_directives == ["发展经济", " 优先补电 "]


def test_capability_blocker_status_text_accepts_snapshot() -> None:
    snapshot = CapabilityStatusSnapshot(
        blocker="missing_prerequisite",
        prerequisite_gap_count=3,
    )

    assert capability_blocker_status_text(snapshot) == "缺少前置建筑 (3)"


def test_capability_snapshot_matches_task_by_label_alias() -> None:
    snapshot = CapabilityStatusSnapshot.from_mapping(
        {
            "task_id": "other-task",
            "task_label": "007",
        }
    )

    assert snapshot.matches_task("task-7", "007", is_capability=True) is True
    assert snapshot.matches_task("task-8", "008", is_capability=True) is False
