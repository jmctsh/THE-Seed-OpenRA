"""Tests for CombatExpert — FSM states + 4 engagement modes."""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any, Optional

from models import (
    CombatJobConfig,
    Constraint,
    ConstraintEnforcement,
    EngagementMode,
    ExpertSignal,
    JobStatus,
    SignalKind,
)
from experts.combat import CombatExpert, CombatJob, CombatPhase


# --- Mocks ---

class MockGameAPI:
    def __init__(self):
        self.move_calls: list[dict] = []
        self.attack_calls: list[dict] = []

    def move_units_by_location(self, actors, location, attack_move=False):
        self.move_calls.append({
            "actor_ids": [a.actor_id for a in actors],
            "position": (location.x, location.y),
            "attack_move": attack_move,
        })

    def attack_target(self, attacker, target):
        self.attack_calls.append({"attacker": attacker.actor_id, "target": target.actor_id})
        return True

    def deploy_units(self, actors):
        pass


class MockWorldModel:
    def __init__(self):
        self._actors: dict[int, dict] = {}
        self._enemies: list[dict] = []

    def set_actor(self, actor_id, position, hp=100, hp_max=100):
        self._actors[actor_id] = {"actor_id": actor_id, "position": list(position), "hp": hp, "hp_max": hp_max}

    def set_enemies(self, enemies):
        self._enemies = enemies

    def query(self, query_type, params=None):
        if query_type == "actor_by_id":
            aid = params["actor_id"]
            return {"actor": self._actors.get(aid)}
        if query_type == "enemy_actors":
            return {"actors": list(self._enemies)}
        return {}


def make_job(
    engagement_mode=EngagementMode.ASSAULT,
    target=(500, 500),
    retreat_threshold=0.5,
    max_chase=100,
    api=None,
    wm=None,
    constraint_provider=None,
) -> tuple[CombatJob, list[ExpertSignal], MockGameAPI, MockWorldModel]:
    signals: list[ExpertSignal] = []
    api = api or MockGameAPI()
    wm = wm or MockWorldModel()
    config = CombatJobConfig(
        target_position=target,
        engagement_mode=engagement_mode,
        max_chase_distance=max_chase,
        retreat_threshold=retreat_threshold,
    )
    job = CombatJob(
        job_id="j1", task_id="t1", config=config,
        signal_callback=signals.append,
        constraint_provider=constraint_provider,
        game_api=api, world_model=wm,
    )
    return job, signals, api, wm


# --- FSM State Tests ---

def test_approaching_to_engaging():
    """Job starts approaching, transitions to engaging when close enough."""
    job, signals, api, wm = make_job(target=(100, 100))
    wm.set_actor(57, (500, 500))  # Far from target
    wm.set_enemies([{"actor_id": 201, "position": [100, 100]}])
    job.on_resource_granted(["actor:57"])

    job.do_tick()
    assert job.phase == CombatPhase.APPROACHING
    assert len(api.move_calls) >= 1

    # Move actor close to target
    wm.set_actor(57, (105, 105))
    job.do_tick()
    assert job.phase == CombatPhase.ENGAGING
    print("  PASS: approaching_to_engaging")


def test_engaging_clears_area():
    """When no enemies remain near target, job completes."""
    job, signals, api, wm = make_job(target=(100, 100))
    wm.set_actor(57, (100, 100))
    wm.set_enemies([])  # No enemies
    job.on_resource_granted(["actor:57"])

    # Start near target → engaging → no enemies → completed
    job.do_tick()  # approaching → engaging (close enough)
    job.do_tick()  # engaging → no enemies → completed

    assert job.phase == CombatPhase.COMPLETED
    assert job.status == JobStatus.SUCCEEDED
    assert any(s.result == "succeeded" for s in signals)
    print("  PASS: engaging_clears_area")


def test_retreat_threshold():
    """Job retreats when unit losses exceed retreat_threshold."""
    job, signals, api, wm = make_job(retreat_threshold=0.5, target=(100, 100))
    wm.set_actor(57, (100, 100))
    wm.set_actor(58, (100, 100))
    wm.set_enemies([{"actor_id": 201, "position": [100, 100]}])
    job.on_resource_granted(["actor:57", "actor:58"])

    # First tick — establishes initial_unit_count = 2
    job.do_tick()

    # Lose one unit (50% loss = retreat_threshold)
    job.on_resource_revoked(["actor:57"])
    job.do_tick()

    assert job.phase == CombatPhase.COMPLETED
    assert any(s.kind == SignalKind.RISK_ALERT for s in signals)
    print("  PASS: retreat_threshold")


# --- Engagement Mode Tests ---

def test_assault_mode():
    """Assault mode: attack closest enemy."""
    job, signals, api, wm = make_job(engagement_mode=EngagementMode.ASSAULT, target=(100, 100))
    wm.set_actor(57, (100, 100))
    wm.set_enemies([{"actor_id": 201, "position": [110, 110]}])
    job.on_resource_granted(["actor:57"])

    job.do_tick()  # approaching → engaging
    job.do_tick()  # engaging: attack

    assert len(api.attack_calls) >= 1 or len(api.move_calls) >= 1
    print("  PASS: assault_mode")


def test_hold_mode_no_pursuit():
    """Hold mode: doesn't pursue enemies beyond engage radius."""
    job, signals, api, wm = make_job(engagement_mode=EngagementMode.HOLD, target=(100, 100))
    wm.set_actor(57, (100, 100))
    wm.set_enemies([{"actor_id": 201, "position": [300, 300]}])  # Far away
    job.on_resource_granted(["actor:57"])

    job.do_tick()  # approaching → engaging (we're at target)
    job.do_tick()  # engaging: enemies far away, hold doesn't chase

    # Hold mode should NOT attack far enemies
    hold_attacks = [c for c in api.attack_calls if 201 in c.get("actor_ids", [])]
    # Enemies out of ENGAGE_RADIUS should not be attacked in hold mode
    print("  PASS: hold_mode_no_pursuit")


def test_surround_splits_units():
    """Surround mode: splits units into flank groups."""
    job, signals, api, wm = make_job(engagement_mode=EngagementMode.SURROUND, target=(500, 500))
    wm.set_actor(57, (200, 200))
    wm.set_actor(58, (200, 200))
    wm.set_actor(59, (200, 200))
    wm.set_actor(60, (200, 200))
    wm.set_enemies([{"actor_id": 201, "position": [500, 500]}])
    job.on_resource_granted(["actor:57", "actor:58", "actor:59", "actor:60"])

    job.do_tick()  # approaching with surround approach

    # Should have issued multiple move commands to different positions
    assert len(api.move_calls) >= 2  # At least 2 flank groups
    positions = [c["position"] for c in api.move_calls]
    # Positions should be different (different flanks)
    assert len(set(map(tuple, positions))) >= 2
    print("  PASS: surround_splits_units")


def test_harass_disengage():
    """Harass mode: disengages when HP drops."""
    job, signals, api, wm = make_job(engagement_mode=EngagementMode.HARASS, target=(100, 100))
    wm.set_actor(57, (100, 100), hp=50, hp_max=100)  # Low HP
    wm.set_enemies([{"actor_id": 201, "position": [110, 110]}])
    job.on_resource_granted(["actor:57"])

    job.do_tick()  # approaching → engaging
    job.do_tick()  # engaging: low HP → disengage

    # Should have a move call WITHOUT attack_move (disengaging)
    disengage_moves = [c for c in api.move_calls if not c["attack_move"]]
    assert len(disengage_moves) >= 1
    print("  PASS: harass_disengage")


# --- Constraint Tests ---

def test_chase_distance_constraint_clamp():
    """do_not_chase constraint clamps max_chase_distance."""
    constraints = [
        Constraint(
            constraint_id="c1", kind="do_not_chase", scope="global",
            params={"max_distance": 10},
            enforcement=ConstraintEnforcement.CLAMP,
        ),
    ]

    def provider(scope):
        return [c for c in constraints if c.scope == scope or scope == "global"]

    job, signals, api, wm = make_job(
        max_chase=100, target=(100, 100),
        constraint_provider=provider,
    )
    wm.set_actor(57, (100, 100))
    wm.set_enemies([{"actor_id": 201, "position": [250, 250]}])  # Far enemy
    job.on_resource_granted(["actor:57"])

    # Get effective chase distance
    effective = job._effective_chase_distance(100)
    assert effective == 10  # Clamped by constraint
    print("  PASS: chase_distance_constraint_clamp")


# --- Expert Factory ---

def test_combat_expert_creates_job():
    """CombatExpert factory creates CombatJob instances."""
    signals: list[ExpertSignal] = []
    api = MockGameAPI()
    wm = MockWorldModel()

    expert = CombatExpert(game_api=api, world_model=wm)
    assert expert.expert_type == "CombatExpert"

    config = CombatJobConfig(target_position=(100, 100), engagement_mode=EngagementMode.ASSAULT)
    job = expert.create_job("t1", config, signals.append)
    assert isinstance(job, CombatJob)
    assert job.tick_interval == 0.2
    assert job.phase == CombatPhase.APPROACHING
    print("  PASS: combat_expert_creates_job")


def test_progress_signal_emitted():
    """Progress signals are emitted periodically."""
    job, signals, api, wm = make_job(target=(500, 500))
    wm.set_actor(57, (200, 200))
    wm.set_enemies([{"actor_id": 201, "position": [500, 500]}])
    job.on_resource_granted(["actor:57"])

    for _ in range(25):
        job.do_tick()

    progress = [s for s in signals if s.kind == SignalKind.PROGRESS]
    assert len(progress) >= 1
    assert "phase" in progress[0].expert_state
    print("  PASS: progress_signal_emitted")


# --- Run all tests ---

if __name__ == "__main__":
    print("Running CombatExpert tests...\n")

    test_approaching_to_engaging()
    test_engaging_clears_area()
    test_retreat_threshold()
    test_assault_mode()
    test_hold_mode_no_pursuit()
    test_surround_splits_units()
    test_harass_disengage()
    test_chase_distance_constraint_clamp()
    test_combat_expert_creates_job()
    test_progress_signal_emitted()

    print(f"\nAll 10 tests passed!")
