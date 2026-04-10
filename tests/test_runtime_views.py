"""Focused tests for runtime projection helpers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime_views import (
    CapabilityStatusSnapshot,
    build_battlefield_snapshot,
    build_runtime_state_snapshot,
)


def test_build_runtime_state_snapshot_normalizes_capability_status() -> None:
    snapshot = build_runtime_state_snapshot(
        active_tasks={"t1": {"label": "001"}},
        active_jobs={"j1": {"task_id": "t1", "expert_type": "EconomyExpert"}},
        resource_bindings={"actor:1": "j1"},
        constraints=[{"constraint_id": "c1", "kind": "leash"}],
        capability_status={"task_id": "t_cap", "label": "001", "phase": "dispatch"},
        unit_reservations=[{"reservation_id": "res1", "task_id": "t1"}],
        timestamp=123.4,
    ).to_dict()

    assert snapshot["active_tasks"]["t1"]["label"] == "001"
    assert snapshot["active_jobs"]["j1"]["expert_type"] == "EconomyExpert"
    assert snapshot["resource_bindings"]["actor:1"] == "j1"
    assert snapshot["constraints"][0]["constraint_id"] == "c1"
    assert snapshot["capability_status"]["task_id"] == "t_cap"
    assert snapshot["capability_status"]["phase"] == "dispatch"
    assert snapshot["unit_reservations"][0]["reservation_id"] == "res1"
    assert snapshot["timestamp"] == 123.4
    print("  PASS: build_runtime_state_snapshot_normalizes_capability_status")


def test_build_runtime_state_snapshot_accepts_capability_snapshot_object() -> None:
    capability = CapabilityStatusSnapshot(task_id="t_cap", task_label="001", phase="fulfilling")
    snapshot = build_runtime_state_snapshot(
        active_tasks={},
        active_jobs={},
        resource_bindings={},
        constraints=[],
        capability_status=capability,
        unit_reservations=[],
        timestamp=5.0,
    ).to_dict()

    assert snapshot["capability_status"]["task_id"] == "t_cap"
    assert snapshot["capability_status"]["label"] == "001"
    assert snapshot["capability_status"]["phase"] == "fulfilling"
    print("  PASS: build_runtime_state_snapshot_accepts_capability_snapshot_object")


def test_build_battlefield_snapshot_normalizes_numeric_fields() -> None:
    snapshot = build_battlefield_snapshot(
        summary="我方2 / 敌方1",
        disposition="stable",
        focus="recon",
        self_units=2,
        enemy_units=1,
        self_combat_value=123.456,
        enemy_combat_value=78.9,
        idle_self_units=1,
        self_combat_units=2,
        committed_combat_units=1,
        free_combat_units=1,
        low_power=False,
        queue_blocked=True,
        recommended_posture="unblock_queue",
        threat_level="medium",
        threat_direction="west",
        base_under_attack=False,
        base_health_summary="stable",
        has_production=True,
        explored_pct=0.42,
        enemy_bases=1,
        enemy_spotted=3,
        frozen_enemy_count=1,
        pending_request_count=2,
        bootstrapping_request_count=1,
        reservation_count=2,
        stale=False,
        capability_status={"task_id": "t_cap"},
    ).to_dict()

    assert snapshot["self_combat_value"] == 123.46
    assert snapshot["enemy_combat_value"] == 78.9
    assert snapshot["queue_blocked"] is True
    assert snapshot["recommended_posture"] == "unblock_queue"
    assert snapshot["capability_status"]["task_id"] == "t_cap"
    print("  PASS: build_battlefield_snapshot_normalizes_numeric_fields")


if __name__ == "__main__":
    print("Running runtime_views tests...\n")
    test_build_runtime_state_snapshot_normalizes_capability_status()
    test_build_runtime_state_snapshot_accepts_capability_snapshot_object()
    test_build_battlefield_snapshot_normalizes_numeric_fields()
    print("\nAll runtime_views tests passed!")
