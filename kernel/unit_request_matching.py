"""Inference and idle-matching helpers for unit requests."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Optional

from models import UnitRequest


def hint_match_score(actor: Any, hint: str) -> int:
    """Score how well an actor matches a request hint."""
    if not hint:
        return 0
    name = getattr(actor, "name", "") or ""
    display = getattr(actor, "display_name", "") or ""
    if name and name in hint:
        return 2
    if display and display in hint:
        return 2
    return 0


def infer_unit_type(
    category: str,
    hint: str,
    *,
    hint_to_unit: Mapping[str, tuple[str, str]],
    category_defaults: Mapping[str, tuple[str, str]],
) -> tuple[Optional[str], Optional[str]]:
    """Infer concrete (unit_type, queue_type) from category + hint."""
    for keyword, (unit_type, queue_type) in hint_to_unit.items():
        if keyword in hint:
            return unit_type, queue_type
    default = category_defaults.get(category)
    if default:
        return default
    return None, None


def available_match_count(
    req: UnitRequest,
    idle_actors: Iterable[Any],
    *,
    category_to_actor_category: Mapping[str, str],
) -> int:
    """Count how many currently idle actors could satisfy a request by category."""
    actor_category = category_to_actor_category.get(req.category)
    matched = [
        actor
        for actor in idle_actors
        if actor_category is None or actor.category.value == actor_category
    ]
    return len(matched)


def sort_pending_requests(
    requests: Iterable[UnitRequest],
    idle_actors: list[Any],
    *,
    category_to_actor_category: Mapping[str, str],
    urgency_weight: Mapping[str, int],
    task_priority_for: Callable[[str], int],
    request_start_goal: Callable[[UnitRequest], int],
) -> list[UnitRequest]:
    """Sort pending requests by urgency, blocking-ness, start-package value, then task priority."""
    return sorted(
        requests,
        key=lambda req: (
            -urgency_weight.get(req.urgency, 1),
            -int(bool(req.blocking)),
            -int((req.fulfilled + available_match_count(
                req,
                idle_actors,
                category_to_actor_category=category_to_actor_category,
            )) >= request_start_goal(req)),
            -task_priority_for(req.task_id),
            req.created_at,
        ),
    )


def matching_idle_actors(
    req: UnitRequest,
    idle_actors: Iterable[Any],
    *,
    category_to_actor_category: Mapping[str, str],
) -> list[Any]:
    """Return idle actors matching the request category filter."""
    actor_category = category_to_actor_category.get(req.category)
    return [
        actor
        for actor in idle_actors
        if actor_category is None or actor.category.value == actor_category
    ]
