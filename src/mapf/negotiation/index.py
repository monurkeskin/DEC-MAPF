"""Incremental occupancy index with the full detector's ordering and semantics."""

from __future__ import annotations

from collections import Counter

from mapf.core.models import Conflict, ConflictType, Path, Point
from mapf.negotiation.conflict import detect_conflicts

Vertex = tuple[int, Point]
Edge = tuple[int, Point, Point]
Entry = tuple[str, str, int, ConflictType, Point, Point | None]


class ConflictIndex:
    """Only changed immutable plans update occupancy; absolute ticks are applied on read.

    Cheap identity checks still cover custom agents that replace a plan without
    notifying the engine. Cached objects are retained, preventing id reuse.
    """

    def __init__(self) -> None:
        self.stats: Counter[str] = Counter()
        self._input_paths: dict[str, Path] = {}
        self._input_goals: dict[str, Point] | None = None
        self._input_shape: tuple[int, bool] | None = None
        self._relative_conflicts: tuple[Conflict, ...] = ()
        self._shape: tuple[int, bool] | None = None
        self._plans: dict[str, tuple[Path, Point | None]] = {}
        self._positions: dict[str, tuple[Point | None, ...]] = {}
        self._vertices: dict[Vertex, set[str]] = {}
        self._edges: dict[Edge, set[str]] = {}
        self._vertex_matches: dict[Vertex, list[Entry]] = {}
        self._edge_matches: dict[Edge, list[Entry]] = {}

    @staticmethod
    def _edge_key(step: int, a: Point, b: Point) -> Edge:
        return (step, a, b) if (a.x, a.y) < (b.x, b.y) else (step, b, a)

    def detect(
        self,
        paths: dict[str, Path],
        current_time: int = 0,
        lookahead_steps: int = 20,
        disappear_at_target: bool = False,
        goals: dict[str, Point] | None = None,
    ) -> list[Conflict]:
        # Rebuilding every occupancy bucket costs more than the reference scan
        # when every actor moves. Reuse unchanged results first; update the
        # occupancy index only for sparse changes in a sufficiently large roster.
        context = (lookahead_steps, disappear_at_target)
        current_goals = goals if disappear_at_target else None
        changed = sum(
            self._input_paths.get(aid) is not path for aid, path in paths.items()
        )
        removed = len(self._input_paths.keys() - paths.keys())
        changed_context = (
            context != self._input_shape or current_goals != self._input_goals
        )
        if not changed and not removed and not changed_context:
            self.stats["result_hits"] += 1
        else:
            self.stats["path_updates"] += changed
            self.stats["path_removals"] += removed
            if (
                changed_context
                or len(paths) < 16
                or changed + removed > len(paths) // 2
            ):
                conflicts = detect_conflicts(
                    paths, 0, lookahead_steps, disappear_at_target, goals
                )
                self._shape = (
                    None  # lazily rebuild occupancy if a later sparse update needs it
                )
                self.stats["full_scans"] += 1
            else:
                conflicts = self._update(
                    paths, 0, lookahead_steps, disappear_at_target, goals
                )
                self.stats["incremental_queries"] += 1
            self._relative_conflicts = tuple(conflicts)
            self._input_paths = dict(paths)
            self._input_goals = (
                dict(current_goals) if current_goals is not None else None
            )
            self._input_shape = context
        if current_time == 0:
            return list(self._relative_conflicts)
        return [
            c.model_copy(update={"time": c.time + current_time})
            for c in self._relative_conflicts
        ]

    def _update(
        self,
        paths: dict[str, Path],
        current_time: int = 0,
        lookahead_steps: int = 20,
        disappear_at_target: bool = False,
        goals: dict[str, Point] | None = None,
    ) -> list[Conflict]:
        end = max(
            0,
            min(
                max((len(p.points) for p in paths.values()), default=0),
                lookahead_steps + 1,
            ),
        )
        shape = (end, disappear_at_target)
        if shape != self._shape:
            self._shape = shape
            self._plans.clear()
            self._positions.clear()
            self._vertices.clear()
            self._edges.clear()
            self._vertex_matches.clear()
            self._edge_matches.clear()
        dirty_v: set[Vertex] = set()
        dirty_e: set[Edge] = set()

        def update(aid: str, points: tuple[Point | None, ...], add: bool) -> None:
            for step, point in enumerate(points):
                if point is None:
                    continue
                vk = (step, point)
                bucket = self._vertices.setdefault(vk, set())
                bucket.add(aid) if add else bucket.discard(aid)
                if not bucket:
                    self._vertices.pop(vk)
                dirty_v.add(vk)
                nxt = points[step + 1] if step + 1 < len(points) else None
                if nxt is not None and nxt != point:
                    ek = (step, point, nxt)
                    bucket = self._edges.setdefault(ek, set())
                    bucket.add(aid) if add else bucket.discard(aid)
                    if not bucket:
                        self._edges.pop(ek)
                    dirty_e.add(self._edge_key(step, point, nxt))

        for aid in self._plans.keys() - paths.keys():
            update(aid, self._positions.pop(aid), False)
            self._plans.pop(aid)
            self.stats["occupancy_path_removals"] += 1
        for aid, path in paths.items():
            goal = goals[aid] if disappear_at_target and goals is not None else None
            previous = self._plans.get(aid)
            if previous is not None and previous[0] is path and previous[1] == goal:
                continue
            if previous is not None:
                update(aid, self._positions[aid], False)
            disappears = disappear_at_target and (
                goals is None or bool(path.points and path.points[-1] == goal)
            )
            points = tuple(
                path.at_time(step, disappear_at_target=disappears)
                for step in range(end)
            )
            self._positions[aid] = points
            self._plans[aid] = (path, goal)
            update(aid, points, True)
            self.stats["occupancy_path_updates"] += 1
        for key in dirty_v:
            ids = sorted(self._vertices.get(key, ()))
            step, point = key
            if len(ids) > 1:
                self._vertex_matches[key] = [
                    (ids[0], aid, step, ConflictType.VERTEX, point, None)
                    for aid in ids[1:]
                ]
            else:
                self._vertex_matches.pop(key, None)
        for edge_key in dirty_e:
            step, first, second = edge_key
            matches: list[Entry] = []
            for source, target in ((first, second), (second, first)):
                opposite = self._edges.get((step, target, source), set())
                for aid in sorted(self._edges.get((step, source, target), ())):
                    previous_ids = [other for other in opposite if other < aid]
                    if previous_ids:
                        # The full scan retains the last preceding reverse-edge user.
                        matches.append(
                            (
                                max(previous_ids),
                                aid,
                                step,
                                ConflictType.EDGE,
                                target,
                                source,
                            )
                        )
            if matches:
                self._edge_matches[edge_key] = matches
            else:
                self._edge_matches.pop(edge_key, None)
        self.stats["vertex_bucket_updates"] += len(dirty_v)
        self.stats["edge_bucket_updates"] += len(dirty_e)
        entries = [
            entry
            for matches in (
                *self._vertex_matches.values(),
                *self._edge_matches.values(),
            )
            for entry in matches
        ]
        entries.sort(
            key=lambda entry: (
                entry[2],
                entry[0],
                entry[1],
                entry[3] != ConflictType.VERTEX,
            )
        )
        return [
            Conflict(
                agent_a=a,
                agent_b=b,
                time=current_time + step,
                conflict_type=kind,
                location_a=pa,
                location_b=pb,
            )
            for a, b, step, kind, pa, pb in entries
        ]
