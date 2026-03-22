"""ReconExpert and ReconJob implementation."""

from __future__ import annotations

from typing import Any, Optional, Protocol

from benchmark import span as bm_span
from models import JobStatus, ReconJobConfig, ResourceKind, ResourceNeed, SignalKind
from openra_api.models import Actor, Location

from .base import BaseJob, ConstraintProvider, ExecutionExpert, SignalCallback


class GameAPILike(Protocol):
    def move_units_by_location(
        self,
        actors: list[Actor],
        location: Location,
        attack_move: bool = False,
    ) -> None:
        ...


class WorldModelLike(Protocol):
    def query(self, query_type: str, params: Optional[dict[str, Any]] = None) -> Any:
        ...


class ReconJob(BaseJob):
    """Autonomous scouting job with simple RTS-style waypoint scoring."""

    tick_interval = 1.0
    _arrival_radius = 32.0

    def __init__(
        self,
        *,
        job_id: str,
        task_id: str,
        config: ReconJobConfig,
        signal_callback: SignalCallback,
        game_api: GameAPILike,
        world_model: WorldModelLike,
        constraint_provider: Optional[ConstraintProvider] = None,
    ) -> None:
        super().__init__(
            job_id=job_id,
            task_id=task_id,
            config=config,
            signal_callback=signal_callback,
            constraint_provider=constraint_provider,
        )
        self.game_api = game_api
        self.world_model = world_model
        self.phase = "searching"
        self._search_index = 0
        self._last_destination: Optional[tuple[int, int]] = None
        self._tracking_target: Optional[tuple[int, int]] = None
        self._tracking_summary_sent = False

    @property
    def expert_type(self) -> str:
        return "ReconExpert"

    def get_resource_needs(self) -> list[ResourceNeed]:
        # Soft constraint: prefer fast units but accept any mobile unit.
        # Kernel allocates fastest available; infantry works if no vehicles.
        return [
            ResourceNeed(
                job_id=self.job_id,
                kind=ResourceKind.ACTOR,
                count=1,
                predicates={"owner": "self"},
            )
        ]

    def tick(self) -> None:
        actor = self._current_actor()
        if actor is None:
            return

        hp_ratio = self._hp_ratio(actor)
        if hp_ratio <= self.config.retreat_hp_pct:
            self._retreat(actor, hp_ratio)
            return

        target = self._find_primary_target()
        if target is not None:
            self._complete_recon(target)
            return

        clue = self._find_tracking_clue()
        if clue is not None:
            self._track_clue(actor, clue)
            return

        self._search(actor)

    def _current_actor(self) -> Optional[dict[str, Any]]:
        for resource_id in self.resources:
            if not resource_id.startswith("actor:"):
                continue
            actor_id = int(resource_id.split(":", 1)[1])
            payload = self.world_model.query("actor_by_id", {"actor_id": actor_id})
            actor = payload.get("actor") if isinstance(payload, dict) else None
            if actor:
                return actor
        return None

    def _search(self, actor: dict[str, Any]) -> None:
        self.phase = "searching"
        with bm_span("expert_logic", name=f"recon:{self.job_id}:search_score"):
            destination = self._choose_search_destination(actor)
        self._move(actor, destination, attack_move=False)

    def _track_clue(self, actor: dict[str, Any], clue: dict[str, Any]) -> None:
        self.phase = "tracking"
        position = tuple(clue.get("position") or actor["position"])
        self._tracking_target = position
        if not self._tracking_summary_sent:
            self.emit_signal(
                kind=SignalKind.PROGRESS,
                summary="发现敌方线索，调整侦察方向",
                expert_state={"phase": self.phase, "progress_pct": 0.4},
                data={"target_type": clue.get("category"), "position": list(position)},
            )
            self._tracking_summary_sent = True
        attack_move = not self.config.avoid_combat
        if self._distance(actor["position"], position) <= 160:
            attack_move = True
        self._move(actor, position, attack_move=attack_move)

    def _retreat(self, actor: dict[str, Any], hp_ratio: float) -> None:
        self.phase = "retreating"
        destination = self._safe_position(actor)
        self.emit_signal(
            kind=SignalKind.RISK_ALERT,
            summary="侦察单位血量过低，开始撤退",
            expert_state={"phase": self.phase, "progress_pct": 0.2},
            data={"hp_ratio": round(hp_ratio, 3), "retreat_to": list(destination)},
        )
        self._move(actor, destination, attack_move=False)

    def _complete_recon(self, target: dict[str, Any]) -> None:
        self.phase = "completed"
        position = tuple(target["position"])
        details = {
            "target_type": self.config.target_type,
            "position": list(position),
            "actor_id": target["actor_id"],
            "name": target.get("name"),
        }
        self.emit_signal(
            kind=SignalKind.TARGET_FOUND,
            summary=f"发现目标 {target.get('display_name') or target.get('name')} at {position}",
            expert_state={"phase": "tracking", "progress_pct": 0.9},
            data=details,
        )
        self.emit_signal(
            kind=SignalKind.TASK_COMPLETE,
            summary=f"侦察完成，发现目标 at {position}",
            world_delta={"target": details},
            expert_state={"phase": self.phase, "progress_pct": 1.0},
            result="succeeded",
            data=details,
        )
        self.status = JobStatus.SUCCEEDED

    def _choose_search_destination(self, actor: dict[str, Any]) -> tuple[int, int]:
        map_info = self.world_model.query("map")
        width = int(map_info.get("width", 2000) or 2000)
        height = int(map_info.get("height", 2000) or 2000)
        candidates = self._candidate_points(width, height)
        scored = sorted(
            candidates,
            key=lambda point: self._score_candidate(point, actor["position"], width, height),
            reverse=True,
        )
        if not scored:
            return actor["position"]
        destination = scored[self._search_index % len(scored)]
        self._search_index += 1
        return destination

    def _candidate_points(self, width: int, height: int) -> list[tuple[int, int]]:
        if self.config.search_region == "northeast":
            return [
                (int(width * 0.82), int(height * 0.18)),
                (int(width * 0.72), int(height * 0.28)),
                (int(width * 0.62), int(height * 0.42)),
            ]
        if self.config.search_region == "enemy_half":
            return [
                (int(width * 0.80), int(height * 0.20)),
                (int(width * 0.78), int(height * 0.72)),
                (int(width * 0.60), int(height * 0.50)),
            ]
        return [
            (int(width * 0.82), int(height * 0.18)),
            (int(width * 0.78), int(height * 0.72)),
            (int(width * 0.20), int(height * 0.22)),
            (int(width * 0.22), int(height * 0.78)),
            (int(width * 0.55), int(height * 0.50)),
        ]

    def _score_candidate(
        self,
        point: tuple[int, int],
        actor_pos: tuple[int, int],
        width: int,
        height: int,
    ) -> float:
        # WorldModel v1 exposes map extents, not an unexplored-cell list. We
        # therefore score scout waypoints heuristically, keeping diagonal-biased
        # RTS scouting priors explicit.
        x, y = point
        center = (width / 2.0, height / 2.0)
        diagonal_bonus = abs((x / max(width, 1)) - (y / max(height, 1)))
        far_side_bonus = x / max(width, 1)
        center_penalty = self._distance(point, center) / max(width + height, 1)
        travel_penalty = self._distance(point, actor_pos) / max(width + height, 1)
        return (diagonal_bonus * 4.0) + (far_side_bonus * 3.0) - center_penalty - (travel_penalty * 0.5)

    def _find_primary_target(self) -> Optional[dict[str, Any]]:
        enemy_payload = self.world_model.query("enemy_actors")
        actors = list(enemy_payload.get("actors", []))
        if self.config.target_type == "base":
            matches = [actor for actor in actors if actor.get("category") == "building"]
        elif self.config.target_type == "army":
            matches = [actor for actor in actors if actor.get("can_attack") and actor.get("category") != "building"]
        else:
            matches = [
                actor
                for actor in actors
                if actor.get("category") in {"building", "mcv"}
            ]
        if not matches:
            return None
        matches.sort(key=lambda actor: actor["actor_id"])
        return matches[0]

    def _find_tracking_clue(self) -> Optional[dict[str, Any]]:
        if self.config.target_type != "base":
            return None
        enemy_payload = self.world_model.query("enemy_actors")
        actors = list(enemy_payload.get("actors", []))
        harvesters = [actor for actor in actors if actor.get("category") == "harvester"]
        if not harvesters:
            return None
        harvesters.sort(key=lambda actor: actor["actor_id"])
        return harvesters[0]

    def _safe_position(self, actor: dict[str, Any]) -> tuple[int, int]:
        buildings = self.world_model.query(
            "my_actors",
            {"category": "building"},
        ).get("actors", [])
        if buildings:
            first = buildings[0]
            return tuple(first["position"])
        map_info = self.world_model.query("map")
        width = int(map_info.get("width", 2000) or 2000)
        height = int(map_info.get("height", 2000) or 2000)
        current_x, current_y = actor["position"]
        return (max(int(width * 0.15), int(current_x * 0.25)), min(int(height * 0.85), current_y))

    def _move(self, actor: dict[str, Any], destination: tuple[int, int], *, attack_move: bool) -> None:
        if self._last_destination == destination and self.phase != "retreating":
            return
        with bm_span("expert_logic", name=f"recon:{self.job_id}:move"):
            unit = Actor(
                actor_id=int(actor["actor_id"]),
                type=actor.get("display_name") or actor.get("name"),
                position=Location(*actor["position"]),
                hppercent=int(actor.get("hp", 100)),
            )
            self.game_api.move_units_by_location(
                [unit],
                Location(*destination),
                attack_move=attack_move,
            )
        self._last_destination = destination

    @staticmethod
    def _hp_ratio(actor: dict[str, Any]) -> float:
        hp = float(actor.get("hp", 100) or 0)
        hp_max = float(actor.get("hp_max", 100) or 100)
        return hp / hp_max if hp_max else 0.0

    @staticmethod
    def _distance(a: tuple[int, int], b: tuple[int, int] | tuple[float, float]) -> float:
        ax, ay = a
        bx, by = b
        return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


class ReconExpert(ExecutionExpert):
    def __init__(self, *, game_api: GameAPILike, world_model: WorldModelLike) -> None:
        self.game_api = game_api
        self.world_model = world_model

    @property
    def expert_type(self) -> str:
        return "ReconExpert"

    def create_job(
        self,
        task_id: str,
        config: ReconJobConfig,
        signal_callback: SignalCallback,
        constraint_provider: Optional[ConstraintProvider] = None,
    ) -> ReconJob:
        return ReconJob(
            job_id=self.generate_job_id(),
            task_id=task_id,
            config=config,
            signal_callback=signal_callback,
            game_api=self.game_api,
            world_model=self.world_model,
            constraint_provider=constraint_provider,
        )
