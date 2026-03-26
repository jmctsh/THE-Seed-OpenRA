"""Tests for ReconExpert and ReconJob."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import JobStatus, ResourceKind, SignalKind, ReconJobConfig
from experts.recon import ReconExpert, ReconJob


class MockGameAPI:
    def __init__(self) -> None:
        self.moves: list[dict] = []

    def move_units_by_location(self, actors, location, attack_move: bool = False) -> None:
        self.moves.append(
            {
                "actor_ids": [actor.actor_id for actor in actors],
                "location": (location.x, location.y),
                "attack_move": attack_move,
            }
        )


class MockWorldModel:
    def __init__(self) -> None:
        self.map_info = {"width": 2000, "height": 1000, "explored_pct": 0.2, "visible_pct": 0.1}
        self.self_actors = {
            57: {
                "actor_id": 57,
                "name": "jeep",
                "display_name": "Jeep",
                "category": "vehicle",
                "position": [120, 820],
                "hp": 100,
                "hp_max": 100,
                "mobility": "fast",
            },
            11: {
                "actor_id": 11,
                "name": "proc",
                "display_name": "Refinery",
                "category": "building",
                "position": [220, 780],
                "hp": 100,
                "hp_max": 100,
                "mobility": "static",
            },
        }
        self.enemy_actors: list[dict] = []

    def query(self, query_type: str, params: dict | None = None):
        params = params or {}
        if query_type == "actor_by_id":
            actor = self.self_actors.get(params["actor_id"])
            return {"actor": dict(actor) if actor else None, "timestamp": 1.0}
        if query_type == "enemy_actors":
            return {"actors": [dict(actor) for actor in self.enemy_actors], "timestamp": 1.0}
        if query_type == "my_actors":
            actors = [dict(actor) for actor in self.self_actors.values()]
            category = params.get("category")
            if category is not None:
                actors = [actor for actor in actors if actor.get("category") == category]
            return {"actors": actors, "timestamp": 1.0}
        if query_type == "map":
            return dict(self.map_info)
        raise ValueError(f"Unsupported query_type: {query_type}")


def make_config(**overrides) -> ReconJobConfig:
    base = {
        "search_region": "enemy_half",
        "target_type": "base",
        "target_owner": "enemy",
        "retreat_hp_pct": 0.3,
        "avoid_combat": True,
    }
    base.update(overrides)
    return ReconJobConfig(**base)


def test_recon_expert_creates_job_with_fast_vehicle_need() -> None:
    api = MockGameAPI()
    world = MockWorldModel()
    expert = ReconExpert(game_api=api, world_model=world)
    signals = []

    job = expert.create_job("t1", make_config(), signals.append)

    assert isinstance(job, ReconJob)
    assert job.expert_type == "ReconExpert"
    needs = job.get_resource_needs()
    assert len(needs) == 1
    assert needs[0].kind == ResourceKind.ACTOR
    assert needs[0].count == 1
    assert needs[0].predicates == {"owner": "self"}  # Soft constraint: any mobile unit
    assert job.tick_interval == 1.0
    print("  PASS: recon_expert_creates_job_with_fast_vehicle_need")


def test_recon_job_scores_search_and_moves_to_diagonal_waypoint() -> None:
    api = MockGameAPI()
    world = MockWorldModel()
    signals = []
    job = ReconJob(
        job_id="j1",
        task_id="t1",
        config=make_config(search_region="northeast"),
        signal_callback=signals.append,
        game_api=api,
        world_model=world,
    )
    job.on_resource_granted(["actor:57"])

    job.tick()

    assert job.phase == "searching"
    assert len(api.moves) == 1
    assert api.moves[0]["actor_ids"] == [57]
    assert api.moves[0]["attack_move"] is False
    x, y = api.moves[0]["location"]
    assert x > 1200
    assert y < 400
    assert signals == []
    print("  PASS: recon_job_scores_search_and_moves_to_diagonal_waypoint")


def test_recon_job_tracks_clue_then_completes_on_base_found() -> None:
    api = MockGameAPI()
    world = MockWorldModel()
    world.enemy_actors = [
        {
            "actor_id": 201,
            "name": "harv",
            "display_name": "Harvester",
            "category": "harvester",
            "position": [1800, 420],
            "can_attack": False,
        }
    ]
    signals = []
    job = ReconJob(
        job_id="j1",
        task_id="t1",
        config=make_config(target_type="base"),
        signal_callback=signals.append,
        game_api=api,
        world_model=world,
    )
    job.on_resource_granted(["actor:57"])

    job.tick()

    assert job.phase == "tracking"
    assert len(api.moves) == 1
    assert api.moves[0]["location"] == (1800, 420)
    assert signals[0].kind == SignalKind.PROGRESS
    assert signals[0].expert_state["phase"] == "tracking"

    world.enemy_actors = [
        {
            "actor_id": 301,
            "name": "proc",
            "display_name": "Refinery",
            "category": "building",
            "position": [1820, 430],
            "can_attack": False,
        }
    ]
    job.tick()

    assert job.status == JobStatus.SUCCEEDED
    assert signals[-2].kind == SignalKind.TARGET_FOUND
    assert signals[-1].kind == SignalKind.TASK_COMPLETE
    assert signals[-1].result == "succeeded"
    assert signals[-1].world_delta["target"]["position"] == [1820, 430]
    print("  PASS: recon_job_tracks_clue_then_completes_on_base_found")


def test_recon_job_retreats_when_hp_below_threshold() -> None:
    api = MockGameAPI()
    world = MockWorldModel()
    world.self_actors[57]["hp"] = 20
    signals = []
    job = ReconJob(
        job_id="j1",
        task_id="t1",
        config=make_config(retreat_hp_pct=0.3),
        signal_callback=signals.append,
        game_api=api,
        world_model=world,
    )
    job.on_resource_granted(["actor:57"])

    job.tick()

    assert job.phase == "retreating"
    assert len(api.moves) == 1
    assert api.moves[0]["attack_move"] is False
    target_x, _ = api.moves[0]["location"]
    assert target_x <= 220
    assert signals[-1].kind == SignalKind.RISK_ALERT
    assert signals[-1].data["hp_ratio"] == 0.2
    print("  PASS: recon_job_retreats_when_hp_below_threshold")


def test_recon_job_keeps_same_destination_until_arrival() -> None:
    api = MockGameAPI()
    world = MockWorldModel()
    signals = []
    job = ReconJob(
        job_id="j1",
        task_id="t1",
        config=make_config(search_region="enemy_half"),
        signal_callback=signals.append,
        game_api=api,
        world_model=world,
    )
    job.on_resource_granted(["actor:57"])

    job.tick()
    first_move = api.moves[-1]["location"]
    job.tick()

    assert job.phase == "searching"
    assert len(api.moves) == 1
    assert api.moves[0]["location"] == first_move
    print("  PASS: recon_job_keeps_same_destination_until_arrival")


def test_recon_job_times_out_to_partial_when_no_base_found() -> None:
    api = MockGameAPI()
    world = MockWorldModel()
    world.map_info["explored_pct"] = 0.20
    signals = []
    job = ReconJob(
        job_id="j1",
        task_id="t1",
        config=make_config(target_type="base"),
        signal_callback=signals.append,
        game_api=api,
        world_model=world,
    )
    job.on_resource_granted(["actor:57"])

    job._created_at -= (job._max_search_duration_s + 1.0)
    world.map_info["explored_pct"] = 0.24
    job.tick()

    assert job.status == JobStatus.SUCCEEDED
    assert signals[-1].kind == SignalKind.TASK_COMPLETE
    assert signals[-1].result == "partial"
    assert signals[-1].data["explored_gain_pct"] >= 0.0
    print("  PASS: recon_job_times_out_to_partial_when_no_base_found")


if __name__ == "__main__":
    print("Running ReconExpert tests...\n")
    test_recon_expert_creates_job_with_fast_vehicle_need()
    test_recon_job_scores_search_and_moves_to_diagonal_waypoint()
    test_recon_job_tracks_clue_then_completes_on_base_found()
    test_recon_job_retreats_when_hp_below_threshold()
    test_recon_job_keeps_same_destination_until_arrival()
    test_recon_job_times_out_to_partial_when_no_base_found()
    print("\nAll 6 ReconExpert tests passed!")
