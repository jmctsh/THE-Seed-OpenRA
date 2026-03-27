"""Structured OpenRA RA knowledge used directly by Experts and Planners."""

from __future__ import annotations

from typing import Any, Protocol

from openra_api.production_names import production_name_matches


class ProductionCapabilityAPI(Protocol):
    def can_produce(self, unit_type: str) -> bool:
        ...


_KNOWLEDGE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "names": ("powr", "发电厂"),
        "roles": ("power_recovery",),
        "downstream_unlocks": ("anypower",),
    },
    {
        "names": ("apwr", "高级发电厂"),
        "roles": ("power_recovery", "tech_gateway"),
        "downstream_unlocks": ("anypower",),
    },
    {
        "names": ("proc", "矿场", "精炼厂", "矿石精炼厂"),
        "roles": ("economy_anchor", "expansion_anchor"),
        "downstream_unlocks": ("harv", "weap", "dome"),
        "economic_effects": ("free_harvester", "refinery_dock", "resource_storage"),
    },
    {
        "names": ("harv", "矿车", "采矿车"),
        "roles": ("resource_collection",),
        "downstream_unlocks": (),
    },
    {
        "names": ("weap", "战车工厂", "车厂"),
        "roles": ("vehicle_gateway", "tech_gateway"),
        "downstream_unlocks": ("fix", "vehicle_production", "mobile_scout_transition", "armor_play"),
    },
    {
        "names": ("fix", "维修厂", "修理厂"),
        "roles": ("repair_gateway", "tech_gateway"),
        "downstream_unlocks": ("mcv",),
    },
    {
        "names": ("mcv", "基地车"),
        "roles": ("expansion_anchor",),
        "downstream_unlocks": ("construction_yard",),
    },
    {
        "names": ("dome", "雷达站", "雷达"),
        "roles": ("awareness_gateway", "tech_gateway"),
        "downstream_unlocks": ("apwr", "agun", "afld", "atek", "stek"),
        "awareness_effects": ("radar_minimap", "online_shroud_reveal", "offline_local_reveal"),
    },
    {
        "names": ("barr", "兵营"),
        "roles": ("infantry_gateway",),
        "downstream_unlocks": ("infantry_production",),
    },
    {
        "names": ("tent", "盟军兵营"),
        "roles": ("infantry_gateway",),
        "downstream_unlocks": ("infantry_production",),
    },
)

LOW_POWER_DISABLE_CLASSES = {
    "low_power": ["ATEK"],
    "low_power_or_powerdown": ["DOME", "TSLA", "AGUN", "SAM"],
    "power_outage_only": ["POWR", "APWR"],
}


def queue_scope_for(queue_type: str | None) -> str:
    if str(queue_type or "").strip():
        return "player_shared"
    return "none"


def knowledge_for_target(unit_type: str | None, queue_type: str | None) -> dict[str, Any]:
    roles: list[str] = []
    downstream_unlocks: list[str] = []
    economic_effects: list[str] = []
    awareness_effects: list[str] = []
    for row in _KNOWLEDGE_ROWS:
        names = row["names"]
        if any(production_name_matches(unit_type, alias, alias) for alias in names):
            roles.extend(row.get("roles", ()))
            downstream_unlocks.extend(row.get("downstream_unlocks", ()))
            economic_effects.extend(row.get("economic_effects", ()))
            awareness_effects.extend(row.get("awareness_effects", ()))
    return {
        "queue_scope": queue_scope_for(queue_type),
        "roles": list(dict.fromkeys(roles)),
        "downstream_unlocks": list(dict.fromkeys(downstream_unlocks)),
        "economic_effects": list(dict.fromkeys(economic_effects)),
        "awareness_effects": list(dict.fromkeys(awareness_effects)),
    }


def has_role(actor: dict[str, Any], role: str) -> bool:
    knowledge = knowledge_for_target(
        actor.get("name") or actor.get("display_name"),
        "Building" if actor.get("category") == "building" else None,
    )
    return role in knowledge.get("roles", [])


def buildable_power_recovery_options(game_api: ProductionCapabilityAPI) -> list[dict[str, str]]:
    return _buildable_options(
        game_api,
        (
            ("powr", "发电厂"),
            ("apwr", "高级发电厂"),
        ),
    )


def buildable_economy_recovery_options(game_api: ProductionCapabilityAPI) -> list[dict[str, str]]:
    return _buildable_options(
        game_api,
        (
            ("proc", "矿场"),
            ("harv", "采矿车"),
        ),
    )


def low_power_impacts() -> dict[str, Any]:
    return {
        "kind": "power_state",
        "effects": ["queue_slowdown", "structure_disable_possible"],
        "disable_classes": LOW_POWER_DISABLE_CLASSES,
    }


def radar_loss_impact() -> dict[str, Any]:
    return {
        "kind": "awareness_loss",
        "effects": ["minimap_unavailable", "reduced_local_awareness"],
    }


def _buildable_options(
    game_api: ProductionCapabilityAPI,
    candidates: tuple[tuple[str, str], ...],
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for unit_type, display_name in candidates:
        try:
            if game_api.can_produce(unit_type):
                options.append({"unit_type": unit_type, "display_name": display_name})
        except Exception:
            continue
    return options
