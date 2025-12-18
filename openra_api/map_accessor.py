from __future__ import annotations

from typing import Any, List

from .models import MapQueryResult


class MapAccessor:
    """统一的地图访问工具，自动处理 row/col major 差异。"""

    def __init__(self, map_info: MapQueryResult) -> None:
        self.map_info = map_info
        self.width = map_info.MapWidth or 0
        self.height = map_info.MapHeight or 0

        explored = map_info.IsExplored or []
        # len == width → [x][y] 列主；否则默认 [y][x] 行主
        self.col_major = bool(explored and self.width > 0 and len(explored) == self.width)

    def _get_cell(self, grid: List[List[Any]], x: int, y: int) -> Any:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return None
        if not grid:
            return None
        try:
            return grid[x][y] if self.col_major else grid[y][x]
        except (IndexError, TypeError):
            return None

    def is_explored(self, x: int, y: int) -> bool:
        return bool(self._get_cell(self.map_info.IsExplored or [], x, y))

    def is_visible(self, x: int, y: int) -> bool:
        return bool(self._get_cell(self.map_info.IsVisible or [], x, y))

    def resource(self, x: int, y: int) -> Any:
        return self._get_cell(self.map_info.Resources or [], x, y)

