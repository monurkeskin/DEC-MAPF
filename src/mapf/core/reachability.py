"""A necessary physical reachability condition, independent of agent policies."""
from __future__ import annotations

from collections.abc import Mapping

from mapf.core.models import Point


class StaticConnectivity:
    """Component labels reused only while the complete obstacle set is unchanged.

    Connectivity is necessary, not sufficient, for MAPF feasibility. Callers must
    include only immutable occupied cells, never movable agents or finite promises.
    """

    def __init__(self, width: int, height: int) -> None:
        self._width = width
        self._height = height
        self._blocked: frozenset[Point] | None = None
        self._labels: dict[tuple[int, int], int] = {}
        self.builds = 0

    def disconnected(
        self,
        positions: Mapping[str, Point],
        goals: Mapping[str, Point],
        blocked: frozenset[Point],
    ) -> list[str]:
        if blocked != self._blocked:
            self._rebuild(blocked)
        result = []
        for agent_id, position in positions.items():
            component = self._labels.get((position.x, position.y))
            goal = goals[agent_id]
            if component is None or component != self._labels.get((goal.x, goal.y)):
                result.append(agent_id)
        return sorted(result)

    def _rebuild(self, blocked: frozenset[Point]) -> None:
        occupied = {(p.x, p.y) for p in blocked}
        labels: dict[tuple[int, int], int] = {}
        for y in range(self._height):
            for x in range(self._width):
                start = (x, y)
                if start in occupied or start in labels:
                    continue
                component = len(labels)
                labels[start] = component
                pending = [start]
                while pending:
                    u, v = pending.pop()
                    for q in ((u - 1, v), (u + 1, v), (u, v - 1), (u, v + 1)):
                        if (0 <= q[0] < self._width and 0 <= q[1] < self._height
                                and q not in occupied and q not in labels):
                            labels[q] = component
                            pending.append(q)
        self._blocked = blocked
        self._labels = labels
        self.builds += 1
