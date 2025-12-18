from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillResult:
    """宏指令执行结果"""

    ok: bool
    need_replan: bool
    reason: str = ""
    actions: List[Dict[str, Any]] = field(default_factory=list)
    observations: Dict[str, Any] = field(default_factory=dict)
    player_message: Optional[str] = None

    @classmethod
    def success(
        cls,
        reason: str = "",
        actions: Optional[List[Dict[str, Any]]] = None,
        observations: Optional[Dict[str, Any]] = None,
        player_message: Optional[str] = None,
        need_replan: bool = False,
    ) -> "SkillResult":
        return cls(
            ok=True,
            need_replan=need_replan,
            reason=reason,
            actions=actions or [],
            observations=observations or {},
            player_message=player_message,
        )

    @classmethod
    def fail(
        cls,
        reason: str,
        actions: Optional[List[Dict[str, Any]]] = None,
        observations: Optional[Dict[str, Any]] = None,
        player_message: Optional[str] = None,
        need_replan: bool = True,
    ) -> "SkillResult":
        return cls(
            ok=False,
            need_replan=need_replan,
            reason=reason,
            actions=actions or [],
            observations=observations or {},
            player_message=player_message,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "need_replan": self.need_replan,
            "reason": self.reason,
            "actions": self.actions,
            "observations": self.observations,
            "player_message": self.player_message,
        }

