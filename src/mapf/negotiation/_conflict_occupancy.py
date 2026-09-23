"""Sparse plan occupancy and deterministic vertex/reverse-edge matches."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from mapf.core.models import Conflict, ConflictType, Path, Point

Vertex = tuple[int, Point]
Edge = tuple[int, Point, Point]
Entry = tuple[str, str, int, ConflictType, Point, Point | None]


def _edge_key(step: int, a: Point, b: Point) -> Edge:
    return (step, a, b) if (a.x, a.y) < (b.x, b.y) else (step, b, a)


def _change_bucket[K](buckets: dict[K, set[str]], key: K, aid: str, add: bool) -> None:
    bucket = buckets.setdefault(key, set())
    if add:
        bucket.add(aid)
    else:
        bucket.discard(aid)
    if not bucket:
        buckets.pop(key)


@dataclass(slots=True)
class _DirtyBuckets:
    vertices: set[Vertex] = field(default_factory=set)
    edges: set[Edge] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _Query:
    paths: dict[str, Path]
    end: int
    disappear_at_target: bool
    goals: dict[str, Point] | None

    def goal(self, aid: str) -> Point | None:
        if self.disappear_at_target and self.goals is not None:
            return self.goals[aid]
        return None

    def positions(self, path: Path, goal: Point | None) -> tuple[Point | None, ...]:
        complete = self.goals is None or bool(path.points and path.points[-1] == goal)
        disappears = self.disappear_at_target and complete
        return tuple(
            path.at_time(t, disappear_at_target=disappears) for t in range(self.end)
        )


class ConflictOccupancy:
    """Own relative occupancy; only recompute matches in changed buckets."""

    def __init__(self, stats: Counter[str]) -> None:
        self._stats = stats
        self._shape: tuple[int, bool] | None = None
        self._plans: dict[str, tuple[Path, Point | None]] = {}
        self._positions: dict[str, tuple[Point | None, ...]] = {}
        self._vertices: dict[Vertex, set[str]] = {}
        self._edges: dict[Edge, set[str]] = {}
        self._vertex_matches: dict[Vertex, list[Entry]] = {}
        self._edge_matches: dict[Edge, list[Entry]] = {}

    def invalidate(self) -> None:
        self._shape = None

    def detect(
        self,
        paths: dict[str, Path],
        horizon: int,
        disappear_at_target: bool,
        goals: dict[str, Point] | None,
    ) -> list[Conflict]:
        end = max(
            0, min(max((len(p.points) for p in paths.values()), default=0), horizon + 1)
        )
        query = _Query(paths, end, disappear_at_target, goals)
        self._reset_shape((end, disappear_at_target))
        dirty = _DirtyBuckets()
        self._remove_absent(paths, dirty)
        self._update_plans(query, dirty)
        self._refresh_matches(dirty)
        return self._conflicts()

    def _reset_shape(self, shape: tuple[int, bool]) -> None:
        if shape == self._shape:
            return
        self._shape = shape
        self._plans.clear()
        self._positions.clear()
        self._vertices.clear()
        self._edges.clear()
        self._vertex_matches.clear()
        self._edge_matches.clear()

    def _remove_absent(self, paths: dict[str, Path], dirty: _DirtyBuckets) -> None:
        for aid in self._plans.keys() - paths.keys():
            self._record_path(aid, self._positions.pop(aid), dirty, add=False)
            self._plans.pop(aid)
            self._stats["occupancy_path_removals"] += 1

    def _update_plans(self, query: _Query, dirty: _DirtyBuckets) -> None:
        for aid, path in query.paths.items():
            goal = query.goal(aid)
            previous = self._plans.get(aid)
            if self._same_plan(previous, path, goal):
                continue
            if previous is not None:
                self._record_path(aid, self._positions[aid], dirty, add=False)
            points = query.positions(path, goal)
            self._positions[aid] = points
            self._plans[aid] = (path, goal)
            self._record_path(aid, points, dirty, add=True)
            self._stats["occupancy_path_updates"] += 1

    @staticmethod
    def _same_plan(
        previous: tuple[Path, Point | None] | None, path: Path, goal: Point | None
    ) -> bool:
        if previous is None:
            return False
        return previous[0] is path and previous[1] == goal

    def _record_path(
        self,
        aid: str,
        points: tuple[Point | None, ...],
        dirty: _DirtyBuckets,
        *,
        add: bool,
    ) -> None:
        for step, point in enumerate(points):
            if point is None:
                continue
            vertex = (step, point)
            _change_bucket(self._vertices, vertex, aid, add)
            dirty.vertices.add(vertex)
            nxt = points[step + 1] if step + 1 < len(points) else None
            if nxt is None or nxt == point:
                continue
            _change_bucket(self._edges, (step, point, nxt), aid, add)
            dirty.edges.add(_edge_key(step, point, nxt))

    def _refresh_matches(self, dirty: _DirtyBuckets) -> None:
        for vertex in dirty.vertices:
            self._match_vertex(vertex)
        for edge in dirty.edges:
            self._match_edge(edge)
        self._stats["vertex_bucket_updates"] += len(dirty.vertices)
        self._stats["edge_bucket_updates"] += len(dirty.edges)

    def _match_vertex(self, key: Vertex) -> None:
        ids = sorted(self._vertices.get(key, ()))
        step, point = key
        if len(ids) > 1:
            self._vertex_matches[key] = [
                (ids[0], aid, step, ConflictType.VERTEX, point, None) for aid in ids[1:]
            ]
        else:
            self._vertex_matches.pop(key, None)

    def _match_edge(self, key: Edge) -> None:
        step, first, second = key
        matches = self._reverse_matches((step, first, second))
        matches.extend(self._reverse_matches((step, second, first)))
        if matches:
            self._edge_matches[key] = matches
        else:
            self._edge_matches.pop(key, None)

    def _reverse_matches(self, edge: Edge) -> list[Entry]:
        step, source, target = edge
        opposite = self._edges.get((step, target, source), set())
        matches: list[Entry] = []
        for aid in sorted(self._edges.get(edge, ())):
            preceding = [other for other in opposite if other < aid]
            if preceding:
                # Retain the full scan's last preceding reverse-edge user.
                matches.append(
                    (max(preceding), aid, step, ConflictType.EDGE, target, source)
                )
        return matches

    def _conflicts(self) -> list[Conflict]:
        entries = [
            entry
            for matches in (
                *self._vertex_matches.values(),
                *self._edge_matches.values(),
            )
            for entry in matches
        ]
        entries.sort(key=lambda e: (e[2], e[0], e[1], e[3] != ConflictType.VERTEX))
        return [
            Conflict(
                agent_a=a,
                agent_b=b,
                time=step,
                conflict_type=kind,
                location_a=pa,
                location_b=pb,
            )
            for a, b, step, kind, pa, pb in entries
        ]
