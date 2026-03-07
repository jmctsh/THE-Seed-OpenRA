"""Expert job configuration schemas — one per Expert type."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReconJobConfig:
    search_region: str  # northeast / enemy_half / full_map
    target_type: str  # base / army / expansion
    target_owner: str  # enemy
    retreat_hp_pct: float = 0.3
    avoid_combat: bool = True


@dataclass
class CombatJobConfig:
    target_position: tuple[int, int]
    engagement_mode: str  # assault / harass / hold / surround
    max_chase_distance: int = 20
    retreat_threshold: float = 0.3


@dataclass
class MovementJobConfig:
    target_position: tuple[int, int]
    move_mode: str = "move"  # move / attack_move / retreat
    arrival_radius: int = 5
    actor_ids: Optional[list[int]] = None  # optional, defaults to ResourceNeed


@dataclass
class DeployJobConfig:
    actor_id: int
    target_position: tuple[int, int]
    building_type: Optional[str] = None  # e.g. "ConstructionYard"


@dataclass
class EconomyJobConfig:
    unit_type: str
    count: int
    queue_type: str
    repeat: bool = False


# Union type for all expert configs
ExpertConfig = (
    ReconJobConfig
    | CombatJobConfig
    | MovementJobConfig
    | DeployJobConfig
    | EconomyJobConfig
)
