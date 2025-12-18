from __future__ import annotations
from typing import Any, Dict

from openra_api.game_api import GameAPI
from openra_api.game_midlayer import RTSMiddleLayer
from the_seed.utils import LogManager

logger = LogManager.get_logger()


class OpenRAEnv:
    """
    OpenRA 观测包装器。
    """

    def __init__(self, api: GameAPI) -> None:
        self.api = api
        # 复用同一个中间层实例以启用缓存
        self.mid = RTSMiddleLayer(api)

    def observe(self) -> str:
        """返回当前游戏状态的文本概要。"""
        snapshot = self._collect_snapshot()
        text = self._format_snapshot(snapshot)
        # logger.debug("OpenRAEnv snapshot=%s", snapshot)
        return text

    def register_actions(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - legacy shim
        logger.warning("register_actions 已废弃：OpenRAEnv 仅提供字符串观测。调用将被忽略。")

    # ---------------- Internal helpers ---------------- #
    def _collect_snapshot(self) -> Dict[str, Any]:
        # 使用新版 intel（brief），避免重复采集 economy/单位统计等信息
        report = self.mid.intel(mode="brief")
        return {
            "report": report,
        }

    def _format_snapshot(self, snapshot: Dict[str, Any]) -> str:
        report = snapshot.get("report") or {}
        econ = report.get("economy") or {}
        tech = report.get("tech") or {}
        combat = report.get("combat") or {}
        opp = report.get("opportunity") or {}
        map_info = report.get("map") or {}
        alerts = report.get("alerts") or []

        best_target = opp.get("best_target")
        best_target_str = (
            f"{best_target.get('type')}@{best_target.get('pos')}" if isinstance(best_target, dict) else "None"
        )

        lines = [
            f"[Intel] t={report.get('t')} stage={report.get('stage')}",
            f"[Economy] cash={econ.get('cash')} power_ok={econ.get('power_ok')} miners={econ.get('miners')} "
            f"refineries={econ.get('refineries')} queue_blocked={econ.get('queue_blocked')}",
            f"[Tech] tier={tech.get('tier')} next_missing={tech.get('next_missing')}",
            f"[Combat] my_value={combat.get('my_value')} enemy_value={combat.get('enemy_value')} "
            f"threat_near_base={combat.get('threat_near_base')} engaged={combat.get('engaged')}",
            f"[Opportunity] best_target={best_target_str} best_score={opp.get('best_score')}",
            f"[Map] explored={map_info.get('explored')} scout_need={map_info.get('scout_need')} "
            f"nearest_resource={map_info.get('nearest_resource')}",
            f"[Alerts] {', '.join(alerts) if alerts else 'none'}",
        ]
        return "\n".join(lines)
