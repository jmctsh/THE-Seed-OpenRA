from __future__ import annotations

from typing import Any, Dict, List, Optional

from .game_api import GameAPI, GameAPIError
from .intel_service import IntelService
from .models import Actor, Location, MapQueryResult
from .skill_result import SkillResult


class MacroActions:
    """宏观技能封装"""

    RALLY_BUILDINGS = ("兵营", "车间", "机场")
    SUPPORT_UNITS = {"矿车", "工程师", "mcv", "基地车"}
    SCOUT_PRIORITY = ("步兵", "狗", "工程师", "火箭兵")

    def __init__(self, api: GameAPI, intel: IntelService) -> None:
        self.api = api
        self.intel_service = intel

    def opening_economy(self) -> SkillResult:
        actions: List[Dict[str, Any]] = []
        try:
            self.api.deploy_mcv_and_wait()
            actions.append({"step": "deploy_mcv"})

            for building in ("电厂", "矿场", "车间"):
                ok = self.api.ensure_can_build_wait(building)
                actions.append({"step": "ensure_building", "name": building, "ok": ok})
                if not ok:
                    return SkillResult.fail(
                        reason=f"无法建造{building}",
                        actions=actions,
                        observations={"missing": building},
                    )
            return SkillResult.success(reason="经济开局就绪", actions=actions)
        except GameAPIError as exc:
            return SkillResult.fail(
                reason=f"经济开局失败: {exc}",
                actions=actions,
                observations={"error": str(exc)},
            )

    def ensure_buildings(self, buildings: List[str]) -> SkillResult:
        actions: List[Dict[str, Any]] = []
        try:
            for name in buildings:
                ok = self.api.ensure_can_build_wait(name)
                actions.append({"building": name, "ok": ok})
                if not ok:
                    return SkillResult.fail(
                        reason=f"无法确保建筑 {name}",
                        actions=actions,
                        observations={"missing": name},
                    )
            return SkillResult.success(reason="所需建筑已准备", actions=actions)
        except GameAPIError as exc:
            return SkillResult.fail(
                reason=f"建造链失败: {exc}",
                actions=actions,
                observations={"error": str(exc)},
            )

    def ensure_units(self, units: Dict[str, int]) -> SkillResult:
        actions: List[Dict[str, Any]] = []
        try:
            for name, count in units.items():
                if count <= 0:
                    continue
                if not self.api.ensure_can_produce_unit(name):
                    return SkillResult.fail(
                        reason=f"无法生产单位 {name}",
                        actions=actions,
                        observations={"missing_prereq": name},
                    )
                self.api.produce_wait(name, count, auto_place_building=True)
                actions.append({"unit": name, "count": count})
            return SkillResult.success(reason="单位生产完成", actions=actions)
        except GameAPIError as exc:
            return SkillResult.fail(
                reason=f"生产单位失败: {exc}",
                actions=actions,
                observations={"error": str(exc)},
            )

    def scout_unexplored(self, max_scouts: int = 1, radius: int = 30) -> SkillResult:
        snapshot = self.intel_service.get_snapshot()
        map_info: Optional[MapQueryResult] = self.intel_service.get_map_info()

        if not map_info:
            return SkillResult.fail(reason="无法获取地图信息", need_replan=False)

        scouts = self._select_scouts(snapshot.get("my_actors", []), max_scouts)
        if not scouts:
            return SkillResult.fail(reason="没有可用侦察单位", need_replan=True)

        base_center = self.intel_service.get_base_center(snapshot)
        try:
            targets = self.api.get_unexplored_nearby_positions(map_info, base_center, radius)
        except GameAPIError as exc:
            return SkillResult.fail(reason=f"侦察路径失败: {exc}", need_replan=False)

        if not targets:
            return SkillResult.success(reason="附近已探索完毕", actions=[], need_replan=False)

        actions: List[Dict[str, Any]] = []
        for actor, target in zip(scouts, targets):
            ok = self.api.move_units_by_location_and_wait([actor], target, max_wait_time=radius / 5)
            actions.append(
                {
                    "unit": getattr(actor, "actor_id", None),
                    "type": getattr(actor, "type", None),
                    "target": target.to_dict(),
                    "ok": ok,
                }
            )

        return SkillResult.success(reason="侦察任务执行完毕", actions=actions)

    def defend_base(self, radius: int = 25) -> SkillResult:
        intel = self.intel_service.get_intel()
        threats = intel.forces.get("enemy", {}).get("threats", [])
        if not threats:
            return SkillResult.success(reason="暂无威胁", player_message="暂无威胁", need_replan=False)

        target_info = threats[0]
        target_pos = target_info.get("pos")
        if not target_pos:
            return SkillResult.fail(reason="威胁数据无效", need_replan=False)

        target_location = Location(target_pos["x"], target_pos["y"])
        snapshot = self.intel_service.get_snapshot()
        defenders = self._select_combat_units(snapshot.get("my_actors", []))

        if not defenders:
            return SkillResult.fail(reason="缺少可用防守单位", need_replan=True)

        try:
            self.api.move_units_by_location(defenders, target_location, attack_move=True)
        except GameAPIError as exc:
            return SkillResult.fail(reason=f"调动防守单位失败: {exc}")

        player_message = f"已派出 {len(defenders)} 个单位防守，目标距基地 {target_info.get('distance')} 格"
        actions = [{"target": target_pos, "defenders": len(defenders)}]
        return SkillResult.success(reason="已执行基地防守", actions=actions, player_message=player_message)

    def rally_production_to(self, pos: Location) -> SkillResult:
        target = pos if isinstance(pos, Location) else Location(pos["x"], pos["y"])
        snapshot = self.intel_service.get_snapshot()
        buildings = [
            actor
            for actor in snapshot.get("my_actors", [])
            if getattr(actor, "type", None) in self.RALLY_BUILDINGS
        ]

        if not buildings:
            return SkillResult.fail(reason="没有可设置集结点的建筑", need_replan=True)

        try:
            self.api.set_rally_point(buildings, target)
        except GameAPIError as exc:
            return SkillResult.fail(reason=f"设置集结点失败: {exc}")

        return SkillResult.success(
            reason="集结点已更新",
            actions=[{"buildings": len(buildings), "pos": target.to_dict()}],
        )

    def _select_scouts(self, actors: List[Actor], max_scouts: int) -> List[Actor]:
        sorted_units = sorted(
            actors,
            key=lambda act: self._scout_priority_index(getattr(act, "type", "")),
        )
        selected = []
        for actor in sorted_units:
            if len(selected) >= max_scouts:
                break
            if getattr(actor, "type", None) is None:
                continue
            selected.append(actor)
        return selected

    def _scout_priority_index(self, unit_type: Optional[str]) -> int:
        if not unit_type:
            return len(self.SCOUT_PRIORITY) + 1
        try:
            return self.SCOUT_PRIORITY.index(unit_type)
        except ValueError:
            return len(self.SCOUT_PRIORITY)

    def _select_combat_units(self, actors: List[Actor]) -> List[Actor]:
        combatants = []
        for actor in actors:
            unit_type = getattr(actor, "type", None)
            if not unit_type:
                continue
            if unit_type.lower() in self.SUPPORT_UNITS or unit_type in self.SUPPORT_UNITS:
                continue
            combatants.append(actor)
        return combatants

