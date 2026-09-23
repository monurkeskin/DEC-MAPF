"""Candidate ordering, collision arbitration and bounded immediate-step repair."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mapf.core.models import Point
from mapf.core.space_time_grid import ReservationTable

if TYPE_CHECKING:
    from mapf.core.protocols import AgentProtocol, EnvironmentProtocol

type Cell = tuple[int, int]


class MoveCandidates:
    """Ordered per-agent choices; recovery may add lateral moves explicitly."""

    def __init__(self, agents: dict[str, AgentProtocol], occupied: dict[Point, str],
                 env: EnvironmentProtocol) -> None:
        self.agents, self.occupied, self.env = agents, occupied, env
        self.current = {aid: agent.current_pos for aid, agent in agents.items()}

    def passable(self, point: Point, aid: str) -> bool:
        if not self.env.is_within_bounds(point) or self.env.is_obstacle(point):
            return False
        return point not in self.occupied or self.occupied[point] == aid

    def lateral(self, aid: str) -> list[Point]:
        current, goal = self.current[aid], self.agents[aid].target_pos
        points = [Point(current.x + dx, current.y + dy)
                  for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]]
        return sorted(points, key=lambda p: abs(p.x - goal.x) + abs(p.y - goal.y))

    def preferred(self, aid: str, desired: Point, allow_wait: bool) -> list[Point]:
        current = self.current[aid]
        choices = []
        if self._admissible_preference(aid, desired, allow_wait):
            choices.append(desired)
        if not allow_wait:
            choices.extend(p for p in self.lateral(aid) if self.passable(p, aid) and p not in choices)
        if current not in choices:
            choices.append(current)
        return choices

    def _admissible_preference(self, aid: str, desired: Point, allow_wait: bool) -> bool:
        current = self.current[aid]
        if abs(desired.x - current.x) + abs(desired.y - current.y) > 1:
            return False
        if not self.passable(desired, aid):
            return False
        return allow_wait or desired != current

    def recovery(self, choices: dict[str, list[Point]], require_progress: bool) -> None:
        for aid in self.agents:
            choices[aid].extend(p for p in self.lateral(aid)
                               if p not in choices[aid] and self.passable(p, aid))
            if require_progress:
                choices[aid].sort(key=lambda p: p == self.current[aid])


class GreedyResolution:
    """Deterministic edge-first arbitration with stationary-cell ownership."""

    def __init__(self, candidates: dict[str, list[Point]], current: dict[str, Point],
                 priority: list[str]) -> None:
        self.candidates = candidates
        self.current = {aid: (p.x, p.y) for aid, p in current.items()}
        self.owners = {cell: aid for aid, cell in self.current.items()}
        self.rank = {aid: index for index, aid in enumerate(priority)}
        self.indices = {aid: 0 for aid in current}
        self.cells = {aid: [(p.x, p.y) for p in points] for aid, points in candidates.items()}

    def yield_agent(self, aid: str) -> None:
        if self.indices[aid] + 1 < len(self.candidates[aid]):
            self.indices[aid] += 1

    def resolve_edge(self, proposals: dict[str, Cell]) -> bool:
        for aid, target in proposals.items():
            peer = self.owners.get(target)
            if peer is None or aid >= peer:
                continue
            if proposals[peer] != self.current[aid]:
                continue
            loser = peer if self.rank[peer] > self.rank[aid] else aid
            self.yield_agent(loser)
            return True
        return False

    def resolve_vertex(self, proposals: dict[str, Cell]) -> bool:
        claims: dict[Cell, list[str]] = {}
        for aid, target in proposals.items():
            claims.setdefault(target, []).append(aid)
        for target, claimants in claims.items():
            if len(claimants) <= 1:
                continue
            for aid in self._vertex_losers(target, claimants):
                self.yield_agent(aid)
            return True
        return False

    def _vertex_losers(self, target: Cell, claimants: list[str]) -> list[str]:
        stationary = next((aid for aid in claimants if self.current[aid] == target), None)
        if stationary is not None:
            return [aid for aid in claimants if aid != stationary]
        return sorted(claimants, key=self.rank.__getitem__)[1:]

    def resolve(self) -> dict[str, Point]:
        for _ in range(len(self.current) * 10 + 50):
            proposals = {aid: self.cells[aid][self.indices[aid]] for aid in self.current}
            if self.resolve_edge(proposals):
                continue
            if not self.resolve_vertex(proposals):
                break
        return {aid: self.candidates[aid][self.indices[aid]] for aid in self.current}


class MoveAuthorization:
    """No-wait and live commitment checks, including permanent goal arrival."""

    def __init__(self, agents: dict[str, AgentProtocol], allow_wait: bool,
                 env: EnvironmentProtocol, tick: int) -> None:
        self.agents, self.allow_wait, self.env, self.tick = agents, allow_wait, env, tick
        self.tables: dict[str, ReservationTable] = {}
        for aid, agent in agents.items():
            table = ReservationTable()
            reserve = getattr(agent, 'reserve_commitments', None)
            if callable(reserve):
                reserve(table, tick)
            self.tables[aid] = table

    def allowed(self, aid: str, point: Point) -> bool:
        table, agent = self.tables[aid], self.agents[aid]
        if not self.allow_wait and point == agent.current_pos:
            return False
        if table.is_vertex_reserved(point, self.tick + 1, aid):
            return False
        if table.is_edge_conflict(agent.current_pos, point, self.tick, aid):
            return False
        if point != agent.target_pos or self.env.config.setting.disappear_at_target:
            return True
        return self.can_park(aid, point)

    def can_park(self, aid: str, point: Point) -> bool:
        table = self.tables[aid]
        for (x, y, tick), owner in table._vertex_reservations.items():
            if (x, y) != (point.x, point.y) or tick < self.tick + 1:
                continue
            if owner != aid:
                return False
        permanent = table._permanent_reservations.get((point.x, point.y))
        return permanent is None or permanent[1] == aid


def candidate_components(candidates: dict[str, list[Point]], current: dict[str, Point],
                         priority: list[str]) -> list[list[str]]:
    """Partition by possible shared cells, retaining deterministic priority order."""
    rank = {aid: index for index, aid in enumerate(priority)}
    cells = {aid: {(p.x, p.y) for p in points} | {(current[aid].x, current[aid].y)}
             for aid, points in candidates.items()}
    owners = _candidate_owners(cells)
    remaining = set(candidates)
    components = []
    for first in priority:
        if first in remaining:
            component = _connected_agents(first, cells, owners, remaining, rank)
            components.append(sorted(component, key=rank.__getitem__))
    return components


def _candidate_owners(cells: dict[str, set[Cell]]) -> dict[Cell, set[str]]:
    owners: dict[Cell, set[str]] = {}
    for aid, points in cells.items():
        for point in points:
            owners.setdefault(point, set()).add(aid)
    return owners


def _connected_agents(first: str, cells: dict[str, set[Cell]], owners: dict[Cell, set[str]],
                      remaining: set[str], rank: dict[str, int]) -> list[str]:
    stack, component = [first], []
    remaining.remove(first)
    while stack:
        aid = stack.pop()
        component.append(aid)
        neighbors = {peer for point in cells[aid] for peer in owners[point]}
        for peer in sorted(neighbors & remaining, key=rank.__getitem__):
            remaining.remove(peer)
            stack.append(peer)
    return component


class JointRepair:
    """Bounded constraint search with a shared node budget across components."""

    def __init__(self, current: dict[str, Point], priority: list[str],
                 max_nodes: int, require_progress: bool) -> None:
        self.current = {aid: (p.x, p.y) for aid, p in current.items()}
        self.rank = {aid: index for index, aid in enumerate(priority)}
        self.max_nodes, self.require_progress = max_nodes, require_progress
        self.nodes = 0
        self.exhausted = False

    def remaining_domains(self, pending: dict[str, list[Cell]], aid: str,
                          target: Cell) -> dict[str, list[Cell]]:
        return {
            peer: [p for p in points if p != target and not (
                target == self.current[peer] and p == self.current[aid]
            )]
            for peer, points in pending.items() if peer != aid
        }

    def search(self, pending: dict[str, list[Cell]], moved: bool = False) -> dict[str, Cell] | None:
        if not pending:
            return {} if moved or not self.require_progress else None
        if any(not points for points in pending.values()):
            return None
        if len({p for points in pending.values() for p in points}) < len(pending):
            return None
        aid = min(pending, key=lambda a: (len(pending[a]), self.rank[a]))
        return self._search_choices(pending, aid, moved)

    def _search_choices(self, pending: dict[str, list[Cell]], aid: str,
                        moved: bool) -> dict[str, Cell] | None:
        for target in pending[aid]:
            if self.nodes >= self.max_nodes:
                self.exhausted = True
                return None
            self.nodes += 1
            rest = self.remaining_domains(pending, aid, target)
            answer = self.search(rest, moved or target != self.current[aid])
            if answer is not None:
                return {aid: target, **answer}
            if self.exhausted:
                return None
        return None

    def status(self, answer: dict[str, Cell] | None) -> str:
        if answer is not None:
            return 'repaired'
        if self.exhausted:
            return 'budget_exhausted'
        return 'progress_unavailable' if self.require_progress else 'immediate_infeasible'

    def resolve(self, components: list[list[str]], admissible: dict[str, list[Point]],
                resolved: dict[str, Point], blocked: set[str]) -> dict[str, Any]:
        outcomes = []
        for component in components:
            if not blocked.intersection(component):
                continue
            before, self.exhausted = self.nodes, False
            domains = {aid: [(p.x, p.y) for p in admissible[aid]] for aid in component}
            answer = self.search(domains)
            if answer is not None:
                resolved.update({aid: Point(*p) for aid, p in answer.items()})
            outcomes.append({'agents': component, 'status': self.status(answer),
                             'search_nodes': self.nodes - before})
        return {
            'node_limit': self.max_nodes, 'search_nodes': self.nodes, 'components': outcomes,
            'remaining_holds': [aid for aid in self.rank
                                if (resolved[aid].x, resolved[aid].y) == self.current[aid]],
        }
