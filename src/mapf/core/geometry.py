"""Bounded immutable static-grid indexes, keyed by full topology content."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType

Cell = tuple[int, int]

@dataclass(frozen=True)
class GridIndex:
    neighbors: Mapping[Cell, tuple[Cell, ...]]
    components: Mapping[Cell, int]

@lru_cache(maxsize=32)
def grid_index(width: int, height: int, obstacles: frozenset[Cell]) -> GridIndex:
    # Preserve the search kernel's historical neighbor order.
    cells = {(x, y) for y in range(height) for x in range(width)} - obstacles
    neighbors = {p: tuple(q for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                          if (q := (p[0] + dx, p[1] + dy)) in cells) for p in sorted(cells)}
    components: dict[Cell, int] = {}
    component = 0
    for start in neighbors:
        if start in components:
            continue
        component += 1
        components[start] = component
        queue = [start]
        for cell in queue:
            for nxt in neighbors[cell]:
                if nxt not in components:
                    components[nxt] = component
                    queue.append(nxt)
    return GridIndex(MappingProxyType(neighbors), MappingProxyType(components))

@lru_cache(maxsize=256)
def goal_distances(width: int, height: int, obstacles: frozenset[Cell], goal: Cell) -> Mapping[Cell, int]:
    geometry = grid_index(width, height, obstacles)
    if goal not in geometry.neighbors:
        return MappingProxyType({})
    distances = {goal: 0}
    queue = [goal]
    for cell in queue:
        for nxt in geometry.neighbors[cell]:
            if nxt not in distances:
                distances[nxt] = distances[cell] + 1
                queue.append(nxt)
    return MappingProxyType(distances)
