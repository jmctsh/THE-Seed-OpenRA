"""Tests for kernel runtime projection helpers."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.runtime_projection import (
    build_active_jobs_projection,
    build_active_tasks_projection,
    build_capability_status_snapshot,
    build_job_stats_by_task,
)
from models import JobStatus, Task, TaskKind, TaskStatus, UnitRequest


class _Controller:
    def __init__(
        self,
        task_id: str,
        expert_type: str,
        status: JobStatus,
        *,
        job_id: str = "job_1",
    ) -> None:
        self.job_id = job_id
        self.task_id = task_id
        self.expert_type = expert_type
        self._status = status

    def to_model(self):
        return SimpleNamespace(status=self._status)


def test_build_capability_status_snapshot_tracks_fulfilling_phase() -> None:
    task = Task(
        task_id="t_cap",
        raw_text="发展经济",
        kind=TaskKind.MANAGED,
        priority=80,
        status=TaskStatus.RUNNING,
        label="001",
        is_capability=True,
    )
    request = UnitRequest(
        request_id="req_1",
        task_id="t_other",
        task_label="002",
        task_summary="补步兵",
        category="infantry",
        count=3,
        urgency="high",
        hint="步兵",
        blocking=False,
        start_released=True,
    )
    snapshot = build_capability_status_snapshot(
        capability_task=task,
        capability_jobs=[_Controller("t_cap", "EconomyExpert", JobStatus.RUNNING)],
        capability_requests=[request],
        unfulfilled_requests=[{"reason": "reinforcement_after_start"}],
        recent_directives=["发展经济"],
    )

    assert snapshot.phase == "fulfilling"
    assert snapshot.blocker == ""
    assert snapshot.start_released_request_count == 1
    assert snapshot.reinforcement_request_count == 1
    assert snapshot.active_job_types == ["EconomyExpert"]
    assert snapshot.recent_directives == ["发展经济"]
    print("  PASS: build_capability_status_snapshot_tracks_fulfilling_phase")


def test_build_capability_status_snapshot_marks_inference_pending() -> None:
    task = Task(
        task_id="t_cap",
        raw_text="发展经济",
        kind=TaskKind.MANAGED,
        priority=80,
        status=TaskStatus.RUNNING,
        label="001",
        is_capability=True,
    )
    request = UnitRequest(
        request_id="req_1",
        task_id="t_other",
        task_label="002",
        task_summary="补兵",
        category="infantry",
        count=1,
        urgency="high",
        hint="来点兵",
    )
    snapshot = build_capability_status_snapshot(
        capability_task=task,
        capability_jobs=[],
        capability_requests=[request],
        unfulfilled_requests=[{"reason": "inference_pending"}],
        recent_directives=[],
    )

    assert snapshot.phase == "dispatch"
    assert snapshot.blocker == "request_inference_pending"
    assert snapshot.inference_pending_count == 1
    assert snapshot.dispatch_request_count == 1
    print("  PASS: build_capability_status_snapshot_marks_inference_pending")


def test_build_capability_status_snapshot_prioritizes_world_sync_stale() -> None:
    task = Task(
        task_id="t_cap",
        raw_text="发展经济",
        kind=TaskKind.MANAGED,
        priority=80,
        status=TaskStatus.RUNNING,
        label="001",
        is_capability=True,
    )
    request = UnitRequest(
        request_id="req_1",
        task_id="t_other",
        task_label="002",
        task_summary="补兵",
        category="infantry",
        count=1,
        urgency="high",
        hint="步兵",
    )
    snapshot = build_capability_status_snapshot(
        capability_task=task,
        capability_jobs=[],
        capability_requests=[request],
        unfulfilled_requests=[{"reason": "world_sync_stale"}],
        recent_directives=[],
    )

    assert snapshot.blocker == "world_sync_stale"
    assert snapshot.world_sync_stale_count == 1
    assert snapshot.dispatch_request_count == 1
    print("  PASS: build_capability_status_snapshot_prioritizes_world_sync_stale")


def test_build_capability_status_snapshot_tracks_producer_disabled() -> None:
    task = Task(
        task_id="t_cap",
        raw_text="发展经济",
        kind=TaskKind.MANAGED,
        priority=80,
        status=TaskStatus.RUNNING,
        label="001",
        is_capability=True,
    )
    request = UnitRequest(
        request_id="req_1",
        task_id="t_other",
        task_label="002",
        task_summary="补坦克",
        category="vehicle",
        count=1,
        urgency="high",
        hint="重坦",
    )
    snapshot = build_capability_status_snapshot(
        capability_task=task,
        capability_jobs=[],
        capability_requests=[request],
        unfulfilled_requests=[{"reason": "producer_disabled"}],
        recent_directives=[],
    )

    assert snapshot.blocker == "producer_disabled"
    assert snapshot.producer_disabled_count == 1
    assert snapshot.dispatch_request_count == 1
    print("  PASS: build_capability_status_snapshot_tracks_producer_disabled")


def test_runtime_projection_helpers_build_active_rows_and_job_stats() -> None:
    active_task = Task(
        task_id="t_active",
        raw_text="侦察",
        kind=TaskKind.MANAGED,
        priority=60,
        status=TaskStatus.RUNNING,
        label="001",
    )
    finished_task = Task(
        task_id="t_done",
        raw_text="完成任务",
        kind=TaskKind.MANAGED,
        priority=30,
        status=TaskStatus.SUCCEEDED,
        label="002",
    )
    controllers = [
        _Controller("t_active", "ReconExpert", JobStatus.RUNNING, job_id="job_run"),
        _Controller("t_active", "ReconExpert", JobStatus.FAILED, job_id="job_fail"),
        _Controller("t_done", "CombatExpert", JobStatus.SUCCEEDED, job_id="job_done"),
    ]

    active_tasks = build_active_tasks_projection(
        tasks=[active_task, finished_task],
        active_actor_ids_for=lambda task_id: [11, 12] if task_id == "t_active" else [99],
    )
    active_jobs = build_active_jobs_projection(controllers)
    job_stats = build_job_stats_by_task(controllers)

    assert active_tasks == {
        "t_active": {
            "raw_text": "侦察",
            "label": "001",
            "kind": TaskKind.MANAGED.value,
            "priority": 60,
            "status": TaskStatus.RUNNING.value,
            "is_capability": False,
            "active_actor_ids": [11, 12],
            "active_group_size": 2,
        }
    }
    assert active_jobs == {
        "job_run": {
            "task_id": "t_active",
            "expert_type": "ReconExpert",
            "status": JobStatus.RUNNING.value,
        }
    }
    assert job_stats == {
        "t_active": {
            "failed_count": 1,
            "expert_attempts": {"ReconExpert": 2},
        },
        "t_done": {
            "failed_count": 0,
            "expert_attempts": {"CombatExpert": 1},
        },
    }
    print("  PASS: runtime_projection_helpers_build_active_rows_and_job_stats")
