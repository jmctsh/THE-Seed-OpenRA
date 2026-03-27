"""CombatExpert — FSM-driven combat with 4 engagement modes (design.md §3).

FSM states: approaching → engaging → pursuing → retreating → completed

Engagement modes:
  - assault: direct attack, full commitment
  - harass: hit-and-run, disengage when pressured
  - hold: defend position, don't chase
  - surround: multi-angle approach, coordinate flanks
"""

from __future__ import annotations

import logging
import math
from enum import Enum
from typing import Any, Optional, Protocol

from models import CombatJobConfig, EngagementMode, JobStatus, SignalKind
from openra_api.models import Actor, Location

from .base import BaseJob, ConstraintProvider, ExecutionExpert, SignalCallback
from .game_api_protocol import GameAPILike
from .knowledge import recon_first_recommendation

logger = logging.getLogger(__name__)


class WorldModelLike(Protocol):
    def query(self, query_type: str, params: Optional[dict[str, Any]] = None) -> Any: ...


# --- FSM States ---

class CombatPhase(str, Enum):
    APPROACHING = "approaching"
    ENGAGING = "engaging"
    PURSUING = "pursuing"
    RETREATING = "retreating"
    COMPLETED = "completed"


# --- Constants ---

_ENGAGE_RADIUS = 60.0  # Distance to switch from approaching → engaging
_PURSUIT_LOST_RADIUS = 200.0  # Distance beyond which pursuit is abandoned
_HARASS_DISENGAGE_HP = 0.6  # HP ratio to disengage in harass mode
_SURROUND_ANGLES = [0, 90, 180, 270]  # Degrees for surround flanks
_SURROUND_OFFSET = 80  # Distance from target for surround approach points


class CombatJob(BaseJob):
    """FSM-driven combat job."""

    tick_interval = 0.2

    def __init__(
        self,
        *,
        job_id: str,
        task_id: str,
        config: CombatJobConfig,
        signal_callback: SignalCallback,
        constraint_provider: Optional[ConstraintProvider] = None,
        game_api: GameAPILike,
        world_model: WorldModelLike,
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
        self.phase = CombatPhase.APPROACHING
        self._tick_count = 0
        self._initial_unit_count = 0
        self._pursuit_origin: Optional[tuple[int, int]] = None
        self._harass_disengage = False
        self._has_seen_enemy = False

    @property
    def expert_type(self) -> str:
        return "CombatExpert"

    def tick(self) -> None:
        self._tick_count += 1
        config: CombatJobConfig = self.config  # type: ignore[assignment]
        actor_ids = self._get_actor_ids()

        if not actor_ids:
            return

        if self._initial_unit_count == 0:
            self._initial_unit_count = len(actor_ids)

        # Check retreat threshold
        if self._should_retreat(actor_ids, config.retreat_threshold):
            self._transition(CombatPhase.RETREATING)

        # Apply constraints
        effective_chase = self._effective_chase_distance(config.max_chase_distance)

        # FSM dispatch
        if self.phase == CombatPhase.APPROACHING:
            self._tick_approaching(actor_ids, config)
        elif self.phase == CombatPhase.ENGAGING:
            self._tick_engaging(actor_ids, config)
        elif self.phase == CombatPhase.PURSUING:
            self._tick_pursuing(actor_ids, config, effective_chase)
        elif self.phase == CombatPhase.RETREATING:
            self._tick_retreating(actor_ids, config)
        elif self.phase == CombatPhase.COMPLETED:
            return

        # Periodic progress signal
        if self._tick_count % 25 == 0:
            self.emit_signal(
                kind=SignalKind.PROGRESS,
                summary=f"Combat phase: {self.phase.value}, units: {len(actor_ids)}",
                expert_state={
                    "phase": self.phase.value,
                    "tick": self._tick_count,
                    "units_remaining": len(actor_ids),
                    "initial_units": self._initial_unit_count,
                },
            )

    # --- FSM tick handlers ---

    def _tick_approaching(self, actor_ids: list[int], config: CombatJobConfig) -> None:
        """Move toward target_position until within engage range."""
        centroid = self._unit_centroid(actor_ids)
        if centroid is None:
            return

        dist = self._distance(centroid, config.target_position)
        if dist <= _ENGAGE_RADIUS:
            self._transition(CombatPhase.ENGAGING)
            self._pursuit_origin = config.target_position
            return

        # Move toward target
        if config.engagement_mode == EngagementMode.SURROUND:
            self._issue_surround_approach(actor_ids, config.target_position)
        else:
            self._move_units(actor_ids, config.target_position, attack_move=True)

    def _tick_engaging(self, actor_ids: list[int], config: CombatJobConfig) -> None:
        """Engage enemies at target position."""
        enemies = self._find_enemies_near(config.target_position, _ENGAGE_RADIUS * 2)

        if not enemies:
            if self._has_seen_enemy:
                self._complete("succeeded", f"Area {config.target_position} cleared")
            else:
                self._complete(
                    "partial",
                    "当前没有可见敌方目标，建议先执行侦察",
                    extra_data={
                        "impact": {"kind": "target_visibility", "effects": ["no_visible_enemy"]},
                        "recommendation": recon_first_recommendation(),
                    },
                )
            return

        self._has_seen_enemy = True

        if config.engagement_mode == EngagementMode.ASSAULT:
            self._engage_assault(actor_ids, enemies)
        elif config.engagement_mode == EngagementMode.HARASS:
            self._engage_harass(actor_ids, enemies, config)
        elif config.engagement_mode == EngagementMode.HOLD:
            self._engage_hold(actor_ids, enemies, config)
        elif config.engagement_mode == EngagementMode.SURROUND:
            self._engage_surround(actor_ids, enemies, config)

    def _tick_pursuing(self, actor_ids: list[int], config: CombatJobConfig, max_chase: int) -> None:
        """Chase retreating enemies within max_chase_distance."""
        if config.engagement_mode == EngagementMode.HOLD:
            # Hold mode never pursues
            self._transition(CombatPhase.ENGAGING)
            return

        enemies = self._find_enemies_near(config.target_position, _PURSUIT_LOST_RADIUS)
        if not enemies:
            self._complete("succeeded", "All enemies eliminated or fled")
            return

        # Check chase distance from original engagement point
        closest_enemy_pos = tuple(enemies[0].get("position", [0, 0]))
        if self._pursuit_origin:
            chase_dist = self._distance(self._pursuit_origin, closest_enemy_pos)
            if chase_dist > max_chase:
                self._transition(CombatPhase.ENGAGING)
                return

        # Continue pursuit
        self._move_units(actor_ids, closest_enemy_pos, attack_move=True)

    def _tick_retreating(self, actor_ids: list[int], config: CombatJobConfig) -> None:
        """Retreat away from target position."""
        centroid = self._unit_centroid(actor_ids)
        if centroid is None:
            self._complete("failed", "All units lost during retreat")
            return

        # Move away from target
        dx = centroid[0] - config.target_position[0]
        dy = centroid[1] - config.target_position[1]
        dist = max(1.0, math.sqrt(dx * dx + dy * dy))
        retreat_pos = (
            int(centroid[0] + dx / dist * 150),
            int(centroid[1] + dy / dist * 150),
        )
        self._move_units(actor_ids, retreat_pos, attack_move=False)

        self.emit_signal(
            kind=SignalKind.RISK_ALERT,
            summary=f"Retreating — losses exceed {config.retreat_threshold:.0%}",
            expert_state={"phase": "retreating", "units_remaining": len(actor_ids)},
        )
        self._complete("partial", "Retreated due to heavy losses")

    # --- Engagement mode implementations ---

    def _engage_assault(self, actor_ids: list[int], enemies: list[dict]) -> None:
        """Assault: all units attack the closest enemy."""
        target = enemies[0]
        target_id = target.get("actor_id")
        if target_id is not None:
            try:
                self._attack_unit(actor_ids, target_id)
            except Exception:
                # Fallback to attack-move toward enemy position
                pos = tuple(target.get("position", [0, 0]))
                self._move_units(actor_ids, pos, attack_move=True)

    def _engage_harass(self, actor_ids: list[int], enemies: list[dict], config: CombatJobConfig) -> None:
        """Harass: attack then disengage if pressured."""
        avg_hp = self._average_hp_ratio(actor_ids)
        if avg_hp < _HARASS_DISENGAGE_HP and not self._harass_disengage:
            # Disengage — move away temporarily
            self._harass_disengage = True
            centroid = self._unit_centroid(actor_ids) or config.target_position
            dx = centroid[0] - config.target_position[0]
            dy = centroid[1] - config.target_position[1]
            dist = max(1.0, math.sqrt(dx * dx + dy * dy))
            disengage_pos = (
                int(centroid[0] + dx / dist * 80),
                int(centroid[1] + dy / dist * 80),
            )
            self._move_units(actor_ids, disengage_pos, attack_move=False)
            return

        if self._harass_disengage:
            # Re-engage after moving away
            self._harass_disengage = False

        # Normal attack
        self._engage_assault(actor_ids, enemies)

    def _engage_hold(self, actor_ids: list[int], enemies: list[dict], config: CombatJobConfig) -> None:
        """Hold: attack enemies that come close, don't move from position."""
        nearby = [e for e in enemies if self._distance(
            tuple(e.get("position", [0, 0])), config.target_position
        ) <= _ENGAGE_RADIUS]
        if nearby:
            self._engage_assault(actor_ids, nearby)
        # else: stay put, don't chase

    def _engage_surround(self, actor_ids: list[int], enemies: list[dict], config: CombatJobConfig) -> None:
        """Surround: split units to attack from multiple angles."""
        if len(actor_ids) < 2:
            # Not enough units to surround — fall back to assault
            self._engage_assault(actor_ids, enemies)
            return

        target_pos = config.target_position
        groups = self._split_into_flanks(actor_ids)

        for i, group in enumerate(groups):
            if not group:
                continue
            angle_rad = math.radians(_SURROUND_ANGLES[i % len(_SURROUND_ANGLES)])
            approach_pos = (
                int(target_pos[0] + _SURROUND_OFFSET * math.cos(angle_rad)),
                int(target_pos[1] + _SURROUND_OFFSET * math.sin(angle_rad)),
            )
            self._move_units(group, approach_pos, attack_move=True)

    def _issue_surround_approach(self, actor_ids: list[int], target_pos: tuple[int, int]) -> None:
        """Approach from multiple angles for surround mode."""
        groups = self._split_into_flanks(actor_ids)
        for i, group in enumerate(groups):
            if not group:
                continue
            angle_rad = math.radians(_SURROUND_ANGLES[i % len(_SURROUND_ANGLES)])
            approach_pos = (
                int(target_pos[0] + _SURROUND_OFFSET * 1.5 * math.cos(angle_rad)),
                int(target_pos[1] + _SURROUND_OFFSET * 1.5 * math.sin(angle_rad)),
            )
            self._move_units(group, approach_pos, attack_move=True)

    # --- Helpers ---

    def _move_units(self, actor_ids: list[int], position: tuple, *, attack_move: bool = False) -> None:
        """Wrapper: convert to real GameAPI call."""
        actors = [Actor(actor_id=aid) for aid in actor_ids]
        loc = Location(x=int(position[0]), y=int(position[1]))
        self.game_api.move_units_by_location(actors, loc, attack_move=attack_move)

    def _attack_unit(self, actor_ids: list[int], target_id: int) -> None:
        """Wrapper: attack a specific enemy unit."""
        for aid in actor_ids:
            self.game_api.attack_target(Actor(actor_id=aid), Actor(actor_id=target_id))

    def _split_into_flanks(self, actor_ids: list[int]) -> list[list[int]]:
        """Split actors into flank groups (2-4 groups based on unit count)."""
        n_groups = min(len(actor_ids), len(_SURROUND_ANGLES))
        groups: list[list[int]] = [[] for _ in range(n_groups)]
        for i, aid in enumerate(actor_ids):
            groups[i % n_groups].append(aid)
        return groups

    def _should_retreat(self, actor_ids: list[int], threshold: float) -> bool:
        """Check if losses exceed retreat threshold."""
        if self.phase in (CombatPhase.RETREATING, CombatPhase.COMPLETED):
            return False
        if self._initial_unit_count == 0:
            return False
        loss_ratio = 1.0 - len(actor_ids) / self._initial_unit_count
        return loss_ratio >= threshold

    def _effective_chase_distance(self, base_distance: int) -> int:
        """Apply constraint clamping to chase distance."""
        constraints = self.get_active_constraints()
        effective = base_distance
        for c in constraints:
            if c.kind == "do_not_chase" and c.enforcement.value == "clamp":
                max_dist = c.params.get("max_distance")
                if max_dist is not None:
                    effective = min(effective, int(max_dist))
        return effective

    def _find_enemies_near(self, position: tuple[int, int], radius: float) -> list[dict]:
        """Query WorldModel for enemy actors near a position."""
        result = self.world_model.query("enemy_actors")
        actors = result.get("actors", []) if isinstance(result, dict) else []
        nearby = []
        for a in actors:
            apos = a.get("position", [0, 0])
            if self._distance(tuple(apos), position) <= radius:
                nearby.append(a)
        nearby.sort(key=lambda a: self._distance(tuple(a.get("position", [0, 0])), position))
        return nearby

    def _unit_centroid(self, actor_ids: list[int]) -> Optional[tuple[int, int]]:
        """Get the centroid position of our units."""
        positions = []
        for aid in actor_ids:
            result = self.world_model.query("actor_by_id", {"actor_id": aid})
            actor = result.get("actor") if isinstance(result, dict) else None
            if actor and actor.get("position"):
                positions.append(actor["position"])
        if not positions:
            return None
        avg_x = sum(p[0] for p in positions) // len(positions)
        avg_y = sum(p[1] for p in positions) // len(positions)
        return (avg_x, avg_y)

    def _average_hp_ratio(self, actor_ids: list[int]) -> float:
        """Get average HP ratio of our units."""
        ratios = []
        for aid in actor_ids:
            result = self.world_model.query("actor_by_id", {"actor_id": aid})
            actor = result.get("actor") if isinstance(result, dict) else None
            if actor:
                hp = float(actor.get("hp", 100))
                hp_max = float(actor.get("hp_max", 100) or 100)
                ratios.append(hp / hp_max if hp_max else 0.0)
        return sum(ratios) / len(ratios) if ratios else 1.0

    def _complete(self, result: str, summary: str, extra_data: Optional[dict[str, Any]] = None) -> None:
        """Complete the combat job."""
        self.phase = CombatPhase.COMPLETED
        if result == "succeeded":
            self.status = JobStatus.SUCCEEDED
        elif result == "failed":
            self.status = JobStatus.FAILED
        else:
            self.status = JobStatus.SUCCEEDED  # partial treated as succeeded
        self.emit_signal(
            kind=SignalKind.TASK_COMPLETE,
            summary=summary,
            result=result,
            data={
                "phase": self.phase.value,
                "ticks": self._tick_count,
                "units_remaining": len(self._get_actor_ids()),
                "initial_units": self._initial_unit_count,
                **(extra_data or {}),
            },
        )

    def _transition(self, new_phase: CombatPhase) -> None:
        if self.phase != new_phase:
            logger.debug("CombatJob %s: %s → %s", self.job_id, self.phase.value, new_phase.value)
            self.phase = new_phase

    def _get_actor_ids(self) -> list[int]:
        ids = []
        for r in self.resources:
            if r.startswith("actor:"):
                try:
                    ids.append(int(r.split(":", 1)[1]))
                except ValueError:
                    pass
        return ids

    @staticmethod
    def _distance(a: tuple, b: tuple) -> float:
        return math.dist((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))


class CombatExpert(ExecutionExpert):
    def __init__(self, *, game_api: GameAPILike, world_model: WorldModelLike) -> None:
        self.game_api = game_api
        self.world_model = world_model

    @property
    def expert_type(self) -> str:
        return "CombatExpert"

    def create_job(
        self,
        task_id: str,
        config: Any,
        signal_callback: SignalCallback,
        constraint_provider: Optional[ConstraintProvider] = None,
    ) -> CombatJob:
        return CombatJob(
            job_id=self.generate_job_id(),
            task_id=task_id,
            config=config,
            signal_callback=signal_callback,
            constraint_provider=constraint_provider,
            game_api=self.game_api,
            world_model=self.world_model,
        )
