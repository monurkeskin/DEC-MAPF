from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator, Mapping
from dataclasses import replace
from typing import Any

from mapf.core._space_time_search import (
    SearchRequest,
    SpaceTimeSearch,
    has_custom_reservations,
)
from mapf.core.models import Path, Point


class CandidateSearchCache:
    """Bounded exact memo owned by one immutable local information view.

    No failed search becomes an infeasibility proof. A hit reuses the identical
    bounded search receipt; callers receive a new list of immutable paths.
    """

    def __init__(self, max_entries: int = 16, max_points: int = 16384) -> None:
        if max_entries < 1 or max_points < 1:
            raise ValueError("Positive candidate cache bounds are required")
        self.max_entries, self.max_points = max_entries, max_points
        self.entries: OrderedDict[tuple[Any, ...], tuple[tuple[Path, ...], str, int]] = OrderedDict()
        self.points = 0
        self.hits = 0
        self.misses = 0

    def get(self, key: tuple[Any, ...]) -> tuple[tuple[Path, ...], str, int] | None:
        value = self.entries.get(key)
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
            self.entries.move_to_end(key)
        return value

    def put(self, key: tuple[Any, ...], paths: list[Path], status: str, expansions: int) -> None:
        size = sum(len(path.points) for path in paths)
        if size > self.max_points:
            return
        previous = self.entries.pop(key, None)
        if previous is not None:
            self.points -= sum(len(path.points) for path in previous[0])
        while self._needs_eviction(size):
            _, old = self.entries.popitem(last=False)
            self.points -= sum(len(path.points) for path in old[0])
        self.entries[key] = (tuple(paths), status, expansions)
        self.points += size

    def _needs_eviction(self, incoming_points: int) -> bool:
        if not self.entries:
            return False
        return len(self.entries) >= self.max_entries or self.points + incoming_points > self.max_points


class ReservationTable:
    """Maintains vertex and edge reservations over space-time using primitive integer tuples."""

    def __init__(self) -> None:
        # (x, y, time) -> agent_id
        self._vertex_reservations: dict[tuple[int, int, int], str] = {}
        # ((x_from, y_from), (x_to, y_to), time) -> agent_id
        self._edge_reservations: dict[tuple[tuple[int, int], tuple[int, int], int], str] = {}
        # Permanent reservations: (x, y) -> (start_time, agent_id)
        self._permanent_reservations: dict[tuple[int, int], tuple[int, str]] = {}

    def reserve_path(
        self, agent_id: str, path: Path, start_time: int = 0, permanent: bool = False
    ) -> None:
        """Reserve all space-time points and edges occupied by an agent."""
        if not path.points:
            return

        for idx, pt in enumerate(path.points):
            t = start_time + idx
            self._vertex_reservations[(pt.x, pt.y, t)] = agent_id

            if idx > 0:
                prev_pt = path.points[idx - 1]
                self._edge_reservations[((prev_pt.x, prev_pt.y), (pt.x, pt.y), t - 1)] = agent_id

        if permanent and path.points:
            final_pt = path.points[-1]
            final_t = start_time + len(path.points) - 1
            self._permanent_reservations[(final_pt.x, final_pt.y)] = (final_t, agent_id)

    def reserve_vertex(self, agent_id: str, location: Point, time: int) -> None:
        """Reserve a single space-time vertex constraint."""
        self._vertex_reservations[(location.x, location.y, time)] = agent_id

    def reserve_edge(self, agent_id: str, from_loc: Point, to_loc: Point, time: int) -> None:
        """Reserve a directed space-time edge constraint."""
        self._edge_reservations[((from_loc.x, from_loc.y), (to_loc.x, to_loc.y), time)] = agent_id

    def is_vertex_reserved(self, p: Point, t: int, ignore_agent_id: str | None = None) -> bool:
        """Check if vertex p is occupied by another agent at time t."""
        agent = self._vertex_reservations.get((p.x, p.y, t))
        if agent is not None and agent != ignore_agent_id:
            return True

        # Check permanent reservations
        perm = self._permanent_reservations.get((p.x, p.y))
        if perm is not None:
            perm_t, perm_agent = perm
            if t >= perm_t and perm_agent != ignore_agent_id:
                return True

        return False

    def is_edge_conflict(
        self, u: Point, v: Point, t: int, ignore_agent_id: str | None = None
    ) -> bool:
        """Edge swap conflict occurs if another agent traverses v -> u at time t -> t+1."""
        opposing_agent = self._edge_reservations.get(((v.x, v.y), (u.x, u.y), t))
        return opposing_agent is not None and opposing_agent != ignore_agent_id

    def clear(self) -> None:
        self._vertex_reservations.clear()
        self._edge_reservations.clear()
        self._permanent_reservations.clear()


def compute_static_distance_table(
    width: int,
    height: int,
    obstacles: set[Point] | set[tuple[int, int]],
    goal: Point | tuple[int, int],
) -> dict[tuple[int, int], int]:
    """Compute static shortest-action distances to the goal using backward BFS.

    Distances ignore other agents and timed reservations, so they are an
    admissible heuristic for the corresponding space-time search.
    """
    gx = goal.x if isinstance(goal, Point) else goal[0]
    gy = goal.y if isinstance(goal, Point) else goal[1]
    obs_set = {(p.x, p.y) if isinstance(p, Point) else p for p in obstacles}

    from mapf.core.geometry import goal_distances
    # Return a private mapping to legacy callers; cached state never escapes mutable.
    return dict(goal_distances(width, height, frozenset(obs_set), (gx, gy)))


class SpaceTimeAStar:
    """Space-Time A* search with vertex and edge conflict avoidance."""

    def __init__(
        self,
        grid_width: int,
        grid_height: int,
        obstacles: set[Point] | None = None,
        candidate_cache: CandidateSearchCache | None = None,
    ) -> None:
        self.width = grid_width
        self.height = grid_height
        self.obstacles: set[Point] = obstacles or set()
        self.last_search_status = "not_started"
        self.last_expansions = 0
        self.candidate_cache = candidate_cache
        self.last_candidate_cache_hit = False

    def is_valid_location(self, p: Point) -> bool:
        return 0 <= p.x < self.width and 0 <= p.y < self.height and p not in self.obstacles

    def search(
        self,
        start: Point,
        goal: Point,
        start_time: int = 0,
        reservation_table: ReservationTable | None = None,
        allow_wait: bool = True,
        max_time_steps: int = 150,
        cell_weights: Mapping[Point, float] | None = None,
        ignore_agent_id: str | None = None,
        max_expansions: int = 2500,
        tie_break_weights: bool = False,
        permanent_at_goal: bool = False,
        heuristic_table: dict[tuple[int, int], int] | None = None,
    ) -> Path | None:
        """Find a bounded conflict-free path, preserving deterministic tie order."""
        self.last_search_status = "invalid_input"
        self.last_expansions = 0
        request = SearchRequest(
            start=start, goal=goal, start_time=start_time,
            reservation_table=reservation_table, allow_wait=allow_wait,
            max_time_steps=max_time_steps, cell_weights=cell_weights,
            ignore_agent_id=ignore_agent_id, max_expansions=max_expansions,
            tie_break_weights=tie_break_weights, permanent_at_goal=permanent_at_goal,
            heuristic_table=heuristic_table,
        )
        execution = SpaceTimeSearch(self.width, self.height, self.obstacles, request)
        result = execution.run()
        self.last_search_status = execution.status
        self.last_expansions = execution.expansions
        return result

    def find_bounded_candidate_paths(
        self,
        start: Point,
        goal: Point,
        start_time: int = 0,
        reservation_table: ReservationTable | None = None,
        allow_wait: bool = True,
        max_extra_steps: int = 1,
        max_candidates: int = 8,
        ignore_agent_id: str | None = None,
        cell_weights: Mapping[Point, float] | None = None,
        tie_break_weights: bool = False,
        max_expansions: int = 2500,
        max_time_steps: int = 150,
        permanent_at_goal: bool = False,
    ) -> list[Path]:
        """Find a pool of conflict-free candidate paths within length <= L_min + max_extra_steps.

        Analogous to Java PopLast.java (where depth = dist + 1), this searches for near-optimal
        alternative routes to evaluate via JAAMAS Algorithm 1.
        """
        request = SearchRequest(
            start=start, goal=goal, start_time=start_time,
            reservation_table=reservation_table, allow_wait=allow_wait,
            max_time_steps=max_time_steps, cell_weights=cell_weights,
            ignore_agent_id=ignore_agent_id, max_expansions=max_expansions,
            tie_break_weights=tie_break_weights, permanent_at_goal=permanent_at_goal,
        )
        cache = self._eligible_cache(reservation_table)
        self.last_candidate_cache_hit = False
        key = self._candidate_key(request, max_extra_steps, max_candidates) if cache is not None else None
        if cache is not None and key is not None:
            cached = cache.get(key)
            if cached is not None:
                paths, self.last_search_status, self.last_expansions = cached
                self.last_candidate_cache_hit = True
                return list(paths)
        candidates = self._candidate_pool(request, max_extra_steps, max_candidates)
        if cache is not None and key is not None:
            cache.put(key, candidates, self.last_search_status, self.last_expansions)
        return candidates

    def _eligible_cache(self, table: ReservationTable | None) -> CandidateSearchCache | None:
        if type(self) is not SpaceTimeAStar or "search" in vars(self):
            return None
        if has_custom_reservations(table):
            return None
        return self.candidate_cache

    def _candidate_key(self, request: SearchRequest, extra: int, count: int) -> tuple[Any, ...]:
        table = request.reservation_table
        reservations = None if table is None else (
            tuple(sorted(table._vertex_reservations.items())),
            tuple(sorted(table._edge_reservations.items())),
            tuple(sorted(table._permanent_reservations.items())),
        )
        return (
            self.width, self.height, tuple(sorted((p.x, p.y) for p in self.obstacles)),
            (request.start.x, request.start.y), (request.goal.x, request.goal.y),
            request.start_time, request.allow_wait, extra, count, request.ignore_agent_id,
            request.tie_break_weights, request.max_expansions, request.max_time_steps,
            request.permanent_at_goal,
            tuple(sorted(((p.x, p.y), weight) for p, weight in (request.cell_weights or {}).items())),
            reservations,
        )

    def _candidate_pool(self, request: SearchRequest, extra: int, count: int) -> list[Path]:
        first = request.search_with(self)
        if first is None:
            return []
        candidates = [first]
        seen = {first.points}
        for index, alternative in self._candidate_branches(first, request, candidates, count):
            elapsed = index + 1
            suffix_request = replace(
                request, start=alternative, start_time=request.start_time + elapsed,
                max_time_steps=max(0, request.max_time_steps - elapsed),
            )
            rest = suffix_request.search_with(self)
            if rest is None:
                continue
            candidate = Path(points=first.points[:index + 1] + rest.points)
            if candidate.length <= first.length + extra and candidate.points not in seen:
                seen.add(candidate.points)
                candidates.append(candidate)
        return candidates

    def _candidate_branches(
        self, first: Path, request: SearchRequest, candidates: list[Path], count: int,
    ) -> Iterator[tuple[int, Point]]:
        moves = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if request.allow_wait:
            moves.append((0, 0))
        for index in range(min(6, len(first.points) - 1)):
            current = first.points[index]
            for dx, dy in moves:
                if len(candidates) >= count:
                    return
                alternative = Point(current.x + dx, current.y + dy)
                if alternative == first.points[index + 1] or not self.is_valid_location(alternative):
                    continue
                if self._branch_reserved(request, current, alternative, index):
                    continue
                yield index, alternative

    @staticmethod
    def _branch_reserved(request: SearchRequest, current: Point, alternative: Point, index: int) -> bool:
        table = request.reservation_table
        if table is None:
            return False
        tick = request.start_time + index
        return (table.is_vertex_reserved(alternative, tick + 1, request.ignore_agent_id)
                or table.is_edge_conflict(current, alternative, tick, request.ignore_agent_id))
