from __future__ import annotations

import heapq
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any

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
        while self.entries and (len(self.entries) >= self.max_entries or self.points + size > self.max_points):
            _, old = self.entries.popitem(last=False)
            self.points -= sum(len(path.points) for path in old[0])
        self.entries[key] = (tuple(paths), status, expansions)
        self.points += size


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
    """Precompute static backward BFS distance to goal cell (O03).

    Provides an admissible, consistent heuristic that significantly reduces node expansions
    in complex topologies without altering path validity or cost.
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
        """Find an optimal or weighted conflict-free path from start to goal.

        Employs integer-primitive state representation (sx, sy, st) for inner-loop search,
        eliminating Pydantic model instantiations and achieving zero-allocation lookup speedup.
        """
        self.last_search_status = "invalid_input"
        self.last_expansions = 0
        horizon_reached = False
        sx, sy = start.x, start.y
        gx, gy = goal.x, goal.y
        obs_set = {(p.x, p.y) for p in self.obstacles}

        if not (0 <= sx < self.width and 0 <= sy < self.height and (sx, sy) not in obs_set):
            return None
        if not (0 <= gx < self.width and 0 <= gy < self.height and (gx, gy) not in obs_set):
            return None

        # Direct O(1) zero-allocation access to primitive integer reservations
        has_res = reservation_table is not None
        v_res = reservation_table._vertex_reservations if reservation_table is not None else {}
        e_res = reservation_table._edge_reservations if reservation_table is not None else {}
        p_res = reservation_table._permanent_reservations if reservation_table is not None else {}

        if has_res:
            occ_start = v_res.get((sx, sy, start_time))
            permanent_start = p_res.get((sx, sy))
            if (occ_start is not None and occ_start != ignore_agent_id) or (
                permanent_start is not None and start_time >= permanent_start[0]
                and permanent_start[1] != ignore_agent_id
            ):
                self.last_search_status = "start_reserved"
                return None

        weights: dict[tuple[int, int], float] | None = None
        if cell_weights:
            weights = {(p.x, p.y): w for p, w in cell_weights.items()}

        h_start = (
            heuristic_table.get((sx, sy), abs(sx - gx) + abs(sy - gy))
            if heuristic_table is not None
            else abs(sx - gx) + abs(sy - gy)
        )
        open_set: list[tuple[float, float, int, int, int, int]] = [
            (float(h_start), 0.0, 0, sx, sy, start_time)
        ]
        came_from: dict[tuple[int, int, int], tuple[int, int, int]] = {}
        g_scores: dict[tuple[int, int, int], float] = {(sx, sy, start_time): 0.0}
        heat_scores: dict[tuple[int, int, int], float] = {(sx, sy, start_time): 0.0}
        visited: set[tuple[int, int, int]] = set()

        tie_breaker = 0
        expansions = 0

        moves = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if allow_wait:
            moves.append((0, 0))

        while open_set:
            expansions += 1
            self.last_expansions = expansions
            if expansions > max_expansions:
                self.last_search_status = "expansion_limit"
                return None

            _f, cur_heat, _, cx, cy, ct = heapq.heappop(open_set)

            if cx == gx and cy == gy:
                # If agent parks permanently at goal, ensure goal vertex is not reserved at any future time >= ct
                can_terminate = True
                if permanent_at_goal and has_res:
                    for (vx, vy, ft), reserved_owner in v_res.items():
                        if vx == gx and vy == gy and ft >= ct and reserved_owner != ignore_agent_id:
                            can_terminate = False
                            break
                    permanent = p_res.get((gx, gy))
                    if permanent and permanent[1] != ignore_agent_id:
                        can_terminate = False

                if can_terminate:
                    # Reconstruct path as immutable Point models
                    path_pts: list[Point] = [Point(x=gx, y=gy)]
                    curr = (gx, gy, ct)
                    while curr in came_from:
                        curr = came_from[curr]
                        path_pts.append(Point(x=curr[0], y=curr[1]))
                    path_pts.reverse()
                    self.last_search_status = "solved"
                    return Path(points=path_pts)
                # Goal arrival is absorbing in our physical contract. A delayed
                # arrival must wait/detour before entering, never depart the goal.
                continue

            st_key = (cx, cy, ct)
            if st_key in visited:
                continue
            visited.add(st_key)

            if ct - start_time >= max_time_steps:
                horizon_reached = True
                continue

            nt = ct + 1

            for dx, dy in moves:
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < self.width and 0 <= ny < self.height):
                    continue
                if (nx, ny) in obs_set:
                    continue

                if has_res:
                    # 1. Vertex collision at nt
                    occ = v_res.get((nx, ny, nt))
                    if occ is not None and occ != ignore_agent_id:
                        continue
                    # 2. Permanent collision at target
                    if (nx, ny) in p_res:
                        pt, paid = p_res[(nx, ny)]
                        if nt >= pt and paid != ignore_agent_id:
                            continue
                    # 3. Edge swap collision at ct -> nt
                    if nx != cx or ny != cy:
                        opp = e_res.get(((nx, ny), (cx, cy), ct))
                        if opp is not None and opp != ignore_agent_id:
                            continue

                step_cost = 1.0
                if weights and not tie_break_weights and (nx, ny) in weights:
                    step_cost += weights[(nx, ny)]

                tent_g = g_scores[st_key] + step_cost
                nxt_heat = cur_heat + (weights[(nx, ny)] if weights and (nx, ny) in weights else 0.0)
                nxt_key = (nx, ny, nt)

                if (
                    nxt_key not in g_scores
                    or tent_g < g_scores[nxt_key]
                    or (tent_g == g_scores[nxt_key] and nxt_heat < heat_scores.get(nxt_key, float("inf")))
                ):
                    g_scores[nxt_key] = tent_g
                    heat_scores[nxt_key] = nxt_heat
                    h_next = (
                        heuristic_table.get((nx, ny), abs(nx - gx) + abs(ny - gy))
                        if heuristic_table is not None
                        else abs(nx - gx) + abs(ny - gy)
                    )
                    tie_breaker += 1
                    came_from[nxt_key] = st_key
                    heapq.heappush(
                        open_set, (tent_g + float(h_next), nxt_heat, tie_breaker, nx, ny, nt)
                    )

        self.last_search_status = "horizon_limit" if horizon_reached else "exhausted"
        return None

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
        builtin_reservations = reservation_table is None or (
            type(reservation_table) is ReservationTable
            and not {"is_vertex_reserved", "is_edge_conflict"}.intersection(vars(reservation_table))
        )
        cache = self.candidate_cache if (
            type(self) is SpaceTimeAStar and "search" not in vars(self)
            and builtin_reservations
        ) else None
        key: tuple[Any, ...] | None = None
        self.last_candidate_cache_hit = False
        if cache is not None:
            key = (self.width, self.height, tuple(sorted((p.x, p.y) for p in self.obstacles)),
                   (start.x, start.y), (goal.x, goal.y), start_time, allow_wait,
                   max_extra_steps, max_candidates, ignore_agent_id, tie_break_weights,
                   max_expansions, max_time_steps, permanent_at_goal,
                   tuple(sorted(((p.x, p.y), weight) for p, weight in (cell_weights or {}).items())),
                   None if reservation_table is None else (
                       tuple(sorted(reservation_table._vertex_reservations.items())),
                       tuple(sorted(reservation_table._edge_reservations.items())),
                       tuple(sorted(reservation_table._permanent_reservations.items()))))
            cached = cache.get(key)
            if cached is not None:
                paths, self.last_search_status, self.last_expansions = cached
                self.last_candidate_cache_hit = True
                return list(paths)

        def finish(paths: list[Path]) -> list[Path]:
            if cache is not None and key is not None:
                cache.put(key, paths, self.last_search_status, self.last_expansions)
            return paths

        p0 = self.search(
            start=start,
            goal=goal,
            start_time=start_time,
            reservation_table=reservation_table,
            allow_wait=allow_wait,
            ignore_agent_id=ignore_agent_id,
            cell_weights=cell_weights,
            tie_break_weights=tie_break_weights,
            max_expansions=max_expansions,
            max_time_steps=max_time_steps,
            permanent_at_goal=permanent_at_goal,
        )
        if p0 is None:
            return finish([])

        candidates: list[Path] = [p0]
        seen: set[tuple[tuple[int, int], ...]] = {
            tuple((p.x, p.y) for p in p0.points)
        }
        l_min = len(p0.points) - 1

        branch_moves = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if allow_wait:
            branch_moves.append((0, 0))

        # Explore alternative branch points along the prefix
        max_branch_depth = min(6, len(p0.points) - 1)
        for i in range(max_branch_depth):
            if len(candidates) >= max_candidates:
                break
            curr_pt = p0.points[i]
            curr_t = start_time + i
            next_pt = p0.points[i + 1]

            for dx, dy in branch_moves:
                if len(candidates) >= max_candidates:
                    break
                alt_pt = Point(x=curr_pt.x + dx, y=curr_pt.y + dy)
                if alt_pt == next_pt or not self.is_valid_location(alt_pt):
                    continue

                alt_t = curr_t + 1
                if reservation_table is not None:
                    if reservation_table.is_vertex_reserved(alt_pt, alt_t, ignore_agent_id):
                        continue
                    if reservation_table.is_edge_conflict(curr_pt, alt_pt, curr_t, ignore_agent_id):
                        continue

                # Search remaining path from alt_pt to goal
                rest = self.search(
                    start=alt_pt,
                    goal=goal,
                    start_time=alt_t,
                    reservation_table=reservation_table,
                    allow_wait=allow_wait,
                    ignore_agent_id=ignore_agent_id,
                    cell_weights=cell_weights,
                    tie_break_weights=tie_break_weights,
                    max_expansions=max_expansions,
                    max_time_steps=max(0, max_time_steps - (alt_t - start_time)),
                    permanent_at_goal=permanent_at_goal,
                )
                if rest is not None:
                    full_pts = list(p0.points[: i + 1]) + list(rest.points)
                    cand = Path(points=full_pts)
                    cand_len = len(cand.points) - 1
                    sig = tuple((p.x, p.y) for p in cand.points)
                    if cand_len <= l_min + max_extra_steps and sig not in seen:
                        seen.add(sig)
                        candidates.append(cand)

        return finish(candidates)
