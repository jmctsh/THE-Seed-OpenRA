from __future__ import annotations

"""对外门面：保持 `python -m openra_api.game_midlayer` 可运行。

实际实现已拆分到多个模块，避免单文件过长。
"""

from .actor_view import ActorView
from .game_api import GameAPI
from .intel_memory import IntelMemory
from .intel_model import IntelModel
from .intel_names import normalize_unit_name
from .intel_serializer import IntelSerializer
from .intel_service import IntelService
from .macro_actions import MacroActions
from .map_accessor import MapAccessor
from .rts_middle_layer import RTSMiddleLayer
from .skill_result import SkillResult


if __name__ == "__main__":
    api = GameAPI("localhost")
    mid = RTSMiddleLayer(api)
    print(mid.intel())
