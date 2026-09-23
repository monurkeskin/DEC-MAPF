"""Primitive search state and constraints behind the public SpaceTimeAStar API."""

from __future__ import annotations

import heapq
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mapf.core.models import Path, Point

if TYPE_CHECKING:
    from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar

type Cell = tuple[int, int]
type State = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """One bounded search, retaining the public API's units and defaults."""

    start: Point
    goal: Point
    start_time: int = 0
    reservation_table: ReservationTable | None = None
    allow_wait: bool = True
    max_time_steps: int = 150
    cell_weights: Mapping[Point, float] | None = None
    ignore_agent_id: str | None = None
    max_expansions: int = 2500
    tie_break_weights: bool = False
    permanent_at_goal: bool = False
    heuristic_table: dict[Cell, int] | None = None

    def search_with(self, planner: SpaceTimeAStar) -> Path | None:
        """Dispatch through the public method so plugin overrides remain active."""
        return planner.search(
            start=self.start,
            goal=self.goal,
            start_time=self.start_time,
            reservation_table=self.reservation_table,
            allow_wait=self.allow_wait,
            max_time_steps=self.max_time_steps,
            cell_weights=self.cell_weights,
            ignore_agent_id=self.ignore_agent_id,
            max_expansions=self.max_expansions,
            tie_break_weights=self.tie_break_weights,
            permanent_at_goal=self.permanent_at_goal,
        )


class ReservationView:
    """Primitive occupancy checks without allocating Point objects in the loop."""

    def __init__(self, request: SearchRequest) -> None:
        table = request.reservation_table
        self.vertices = table._vertex_reservations if table is not None else {}
        self.edges = table._edge_reservations if table is not None else {}
        self.permanent = table._permanent_reservations if table is not None else {}
        self.ignored = request.ignore_agent_id

    def occupied(self, cell: Cell, tick: int) -> bool:
        owner = self.vertices.get((*cell, tick))
        if owner is not None and owner != self.ignored:
            return True
        permanent = self.permanent.get(cell)
        if permanent is None or permanent[1] == self.ignored:
            return False
        return tick >= permanent[0]

    def blocks_move(self, origin: Cell, target: Cell, tick: int) -> bool:
        if self.occupied(target, tick + 1):
            return True
        if origin == target:
            return False
        owner = self.edges.get((target, origin, tick))
        return owner is not None and owner != self.ignored

    def can_park(self, cell: Cell, tick: int) -> bool:
        permanent = self.permanent.get(cell)
        if permanent is not None and permanent[1] != self.ignored:
            return False
        return not any(
            (x, y) == cell and time >= tick and owner != self.ignored
            for (x, y, time), owner in self.vertices.items()
        )


def has_custom_reservations(table: ReservationTable | None) -> bool:
    """Only the unmodified built-in table admits primitive occupancy shortcuts."""
    from mapf.core.space_time_grid import ReservationTable

    if table is None:
        return False
    return type(table) is not ReservationTable or bool(
        {"is_vertex_reserved", "is_edge_conflict"}.intersection(vars(table))
    )


class CustomReservationView(ReservationView):
    """Honor extension queries; indefinite parking needs an explicit predicate."""

    def __init__(self, request: SearchRequest) -> None:
        super().__init__(request)
        assert request.reservation_table is not None
        self.table = request.reservation_table

    def occupied(self, cell: Cell, tick: int) -> bool:
        return self.table.is_vertex_reserved(Point(*cell), tick, self.ignored)

    def blocks_move(self, origin: Cell, target: Cell, tick: int) -> bool:
        return self.occupied(target, tick + 1) or self.table.is_edge_conflict(
            Point(*origin), Point(*target), tick, self.ignored
        )

    def can_park(self, cell: Cell, tick: int) -> bool:
        predicate = getattr(self.table, "can_park", None)
        if not callable(predicate):
            raise TypeError(
                "Custom reservations require can_park(location, tick, ignore_agent_id) for permanent goals"
            )
        return bool(predicate(Point(*cell), tick, self.ignored))


class SearchFrontier:
    """Ordered A* frontier, scores and parent links for one search only."""

    def __init__(self, start: State, heuristic: int) -> None:
        self.queue: list[tuple[float, float, int, int, int, int]] = [
            (float(heuristic), 0.0, 0, *start)
        ]
        self.parents: dict[State, State] = {}
        self.costs = {start: 0.0}
        self.heat = {start: 0.0}
        self.visited: set[State] = set()

    def relaxation(
        self, goal: Cell, table: dict[Cell, int] | None
    ) -> Callable[[State, State, float, float], None]:
        """Own score replacement and heap order in one bound operation.

        Binding once avoids repeated attribute lookups in the hot loop. The
        sequence counts accepted improvements, including replacements, so equal
        priorities keep the same deterministic ordering.
        """
        costs, heats, parents, queue = self.costs, self.heat, self.parents, self.queue
        gx, gy = goal
        push = heapq.heappush
        sequence = 0

        def offer(origin: State, target: State, cost: float, heat: float) -> None:
            nonlocal sequence
            previous = costs.get(target)
            better = previous is None or cost < previous
            same_cost_cooler = cost == previous and heat < heats.get(
                target, float("inf")
            )
            if not (better or same_cost_cooler):
                return
            costs[target], heats[target], parents[target] = cost, heat, origin
            x, y, tick = target
            heuristic = abs(x - gx) + abs(y - gy)
            if table is not None:
                heuristic = table.get((x, y), heuristic)
            sequence += 1
            push(queue, (cost + float(heuristic), heat, sequence, x, y, tick))

        return offer

    def path_to(self, state: State) -> Path:
        points = [Point(state[0], state[1])]
        while state in self.parents:
            state = self.parents[state]
            points.append(Point(state[0], state[1]))
        points.reverse()
        return Path(points=points)


class SpaceTimeSearch:
    """A bounded search execution; it does not own candidate memoization."""

    def __init__(
        self, width: int, height: int, obstacles: set[Point], request: SearchRequest
    ) -> None:
        self.width, self.height = width, height
        self.obstacles = {(p.x, p.y) for p in obstacles}
        self.request = request
        self.goal = (request.goal.x, request.goal.y)
        custom = has_custom_reservations(request.reservation_table)
        self.reservations = (
            CustomReservationView(request) if custom else ReservationView(request)
        )
        self.has_reservations = custom or bool(
            self.reservations.vertices
            or self.reservations.edges
            or self.reservations.permanent
        )
        self.weights = {(p.x, p.y): w for p, w in (request.cell_weights or {}).items()}
        self.moves = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if request.allow_wait:
            self.moves.append((0, 0))
        self.status = "invalid_input"
        self.expansions = 0
        self.horizon_reached = False

    def valid(self, cell: Cell) -> bool:
        x, y = cell
        return (
            0 <= x < self.width and 0 <= y < self.height and cell not in self.obstacles
        )

    def heuristic(self, cell: Cell) -> int:
        manhattan = abs(cell[0] - self.goal[0]) + abs(cell[1] - self.goal[1])
        table = self.request.heuristic_table
        return manhattan if table is None else table.get(cell, manhattan)

    def _initial_frontier(self) -> SearchFrontier | None:
        request = self.request
        start_cell = (request.start.x, request.start.y)
        if not self.valid(start_cell) or not self.valid(self.goal):
            return None
        if self.reservations.occupied(start_cell, request.start_time):
            self.status = "start_reserved"
            return None
        return SearchFrontier(
            (*start_cell, request.start_time), self.heuristic(start_cell)
        )

    def run(self) -> Path | None:
        frontier = self._initial_frontier()
        if frontier is None:
            return None
        expand = self._expander(frontier)
        pop = heapq.heappop
        max_expansions = self.request.max_expansions
        goal, can_finish, can_expand = self.goal, self.can_finish, self._can_expand
        while frontier.queue:
            self.expansions += 1
            if self.expansions > max_expansions:
                self.status = "expansion_limit"
                return None
            _, heat, _, x, y, tick = pop(frontier.queue)
            state = (x, y, tick)
            at_goal = (x, y) == goal
            if at_goal and can_finish(tick):
                self.status = "solved"
                return frontier.path_to(state)
            # Arrival is absorbing: delay before entering, never leave a goal.
            if not at_goal and can_expand(state, frontier):
                expand(state, heat)
        self.status = "horizon_limit" if self.horizon_reached else "exhausted"
        return None

    def _can_expand(self, state: State, frontier: SearchFrontier) -> bool:
        if state in frontier.visited:
            return False
        frontier.visited.add(state)
        if state[2] - self.request.start_time >= self.request.max_time_steps:
            self.horizon_reached = True
            return False
        return True

    def can_finish(self, tick: int) -> bool:
        return not self.request.permanent_at_goal or self.reservations.can_park(
            self.goal, tick
        )

    def _expander(self, frontier: SearchFrontier) -> Callable[[State, float], None]:
        """Check legal successors; the frontier owns dominance and priority."""
        width, height, obstacles = self.width, self.height, self.obstacles
        costs = frontier.costs
        weights, tie_heat = self.weights, self.request.tie_break_weights
        has_reservations, blocked = self.has_reservations, self.reservations.blocks_move
        offer = frontier.relaxation(self.goal, self.request.heuristic_table)
        moves = self.moves

        def expand(state: State, heat: float) -> None:
            x, y, tick = state
            base_cost = costs[state]
            for dx, dy in moves:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                cell = (nx, ny)
                if cell in obstacles:
                    continue
                if has_reservations and blocked((x, y), cell, tick):
                    continue
                weight = weights.get(cell, 0.0)
                step_cost = 1.0 if tie_heat else 1.0 + weight
                offer(state, (nx, ny, tick + 1), base_cost + step_cost, heat + weight)

        return expand
