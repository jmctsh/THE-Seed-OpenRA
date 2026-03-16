"""Unified GameAPI Protocol for all Experts.

Maps to the real openra_api.game_api.GameAPI interface.
Experts import this instead of defining their own ad-hoc protocols.
"""

from __future__ import annotations

from typing import List, Protocol

from openra_api.models import Actor, Location


class GameAPILike(Protocol):
    """Minimal GameAPI interface used by Execution Experts."""

    def move_units_by_location(
        self, actors: List[Actor], location: Location, attack_move: bool = False
    ) -> None: ...

    def deploy_units(self, actors: List[Actor]) -> None: ...

    def attack_target(self, attacker: Actor, target: Actor) -> bool: ...
