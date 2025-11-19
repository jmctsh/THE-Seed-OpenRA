from __future__ import annotations
from typing import Any, Dict, List
import time

# —— 引用你的游戏 API —— 
from openra_api.game_api import GameAPI
from openra_api.models import Location, TargetsQueryParam, Actor

# —— 引用 the-seed 抽象 —— 
from the_seed.core.protocol import EnvObservation, ActionSpec, ActionParamSpec
from the_seed.core.registry import ActionRegistry
from the_seed.utils.log_manager import LogManager

logger = LogManager.get_logger()

class OpenRAEnv:
    """把 OpenRA 的状态/动作/事件 适配为 the-seed 可用接口。"""

    def __init__(self, api: GameAPI) -> None:
        self.api = api

    # === 观测构建 ===
    def observe(self) -> EnvObservation:
        logger.debug("OpenRAEnv.observe 开始拉取观测")
        # 这里是一个「轻量但实用」的观测示例；按需扩充
        base = self.api.player_base_info_query()
        screen = self.api.screen_info_query()
        cps = self.api.control_point_query() if hasattr(self.api, "control_point_query") else None

        # 可按需过滤：我方、可见单位等
        my_units = self.api.query_actor(TargetsQueryParam(faction="自己"))
        visible = [
            {
                "id": u.actor_id,
                "type": getattr(u, "type", "?"),
                "hp": getattr(u, "hp_percent", -1),
                "pos": {"x": u.position.x, "y": u.position.y} if getattr(u, "position", None) else None
            }
            for u in my_units
        ]

        observation = EnvObservation(
            timestamp=time.time(),
            screen={
                "min": {"x": screen.ScreenMin.x, "y": screen.ScreenMin.y},
                "max": {"x": screen.ScreenMax.x, "y": screen.ScreenMax.y},
                "mouse": {"x": screen.MousePosition.x, "y": screen.MousePosition.y},
            },
            base={
                "cash": base.Cash,
                "power": base.Power,
                "powerProvided": base.PowerProvided,
                "powerDrained": base.PowerDrained
            },
            visible_units=visible,
            control_points=(cps.ControlPoints if cps else []),
            custom={}
        )
        logger.info(
            "Observation 更新：cash=%s power=%s units=%s cps=%s",
            base.Cash,
            base.Power,
            len(visible),
            len(cps.ControlPoints) if cps else 0,
        )
        logger.debug("Observation payload=%s", observation)
        return observation

    # === 动作注册（提供实现） ===
    def register_actions(self, reg: ActionRegistry) -> None:
        logger.info("开始注册 OpenRAEnv actions")
        # MoveTo：移动我方若干单位到某坐标
        reg.register(ActionSpec(
            name="MoveTo",
            desc="Move selected units to a location",
            params=[
                ActionParamSpec("unit_ids", "array", True, "list of unit actor ids"),
                ActionParamSpec("x", "integer", True, "target x"),
                ActionParamSpec("y", "integer", True, "target y"),
                ActionParamSpec("attack_move", "boolean", False, "attack-move or normal move"),
            ],
            returns="bool"
        ))
        reg.get("MoveTo").impl = self._act_move_to

        # Attack：指定一对一攻击
        reg.register(ActionSpec(
            name="Attack",
            desc="Attack target unit",
            params=[
                ActionParamSpec("attacker_id", "integer", True, "attacker actor id"),
                ActionParamSpec("target_id", "integer", True, "target actor id"),
            ],
            returns="bool"
        ))
        reg.get("Attack").impl = self._act_attack

        # Produce：生产单位
        reg.register(ActionSpec(
            name="Produce",
            desc="Produce a unit type by name",
            params=[
                ActionParamSpec("unit_type", "string", True, "中文名称，如 '步兵'"),
                ActionParamSpec("quantity", "integer", True, "数量"),
                ActionParamSpec("auto_place_building", "boolean", False, "建筑自动放置"),
            ],
            returns="bool"
        ))
        reg.get("Produce").impl = self._act_produce

        # PlaceBuilding：放置顶端建筑
        reg.register(ActionSpec(
            name="PlaceBuilding",
            desc="Place ready building from queue",
            params=[
                ActionParamSpec("queue_type", "string", True, "Building/Defense/..."),
                ActionParamSpec("x", "integer", False, "x"),
                ActionParamSpec("y", "integer", False, "y"),
            ],
            returns="bool"
        ))
        reg.get("PlaceBuilding").impl = self._act_place_building
        action_names = [spec.name for spec in reg.list_specs()]
        logger.info("OpenRAEnv actions 注册完成：%s", ", ".join(action_names))

    # —— 具体动作实现 —— 
    def _act_move_to(self, *, context, unit_ids: List[int], x: int, y: int, attack_move: bool = False) -> bool:
        logger.info("执行 MoveTo：units=%s target=(%s,%s) attack_move=%s", unit_ids, x, y, attack_move)
        actors = [Actor(uid) for uid in unit_ids]
        # 更新一下以获得合法位置（可选）
        for a in actors:
            self.api.update_actor(a)
        self.api.move_units_by_location(actors, Location(x, y), attack_move=attack_move)
        return True

    def _act_attack(self, *, context, attacker_id: int, target_id: int) -> bool:
        logger.info("执行 Attack：attacker=%s target=%s", attacker_id, target_id)
        attacker = Actor(attacker_id)
        target = Actor(target_id)
        self.api.update_actor(attacker)
        self.api.update_actor(target)
        result = self.api.attack_target(attacker, target)
        logger.debug("Attack 结果=%s", result)
        return result

    def _act_produce(self, *, context, unit_type: str, quantity: int, auto_place_building: bool = False) -> bool:
        logger.info(
            "执行 Produce：unit_type=%s quantity=%s auto_place=%s",
            unit_type,
            quantity,
            auto_place_building,
        )
        if not self.api.ensure_can_produce_unit(unit_type):
            logger.warning("Produce 失败：unit=%s 当前不可生产", unit_type)
            return False
        wait_id = self.api.produce(unit_type, quantity, auto_place_building)
        result = wait_id is not None
        logger.debug("Produce 返回 wait_id=%s result=%s", wait_id, result)
        return result

    def _act_place_building(self, *, context, queue_type: str, x: int | None = None, y: int | None = None) -> bool:
        logger.info(
            "执行 PlaceBuilding：queue=%s pos=%s",
            queue_type,
            (x, y) if x is not None and y is not None else "auto",
        )
        if x is not None and y is not None:
            self.api.place_building(queue_type, Location(x, y))
        else:
            self.api.place_building(queue_type)  # 自动位置
        return True