from __future__ import annotations

import heapq
import time
from collections.abc import Iterator

from mapf.core.models import Conflict, Path, Point, SimulationConfig
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar
from mapf.negotiation.conflict import find_first_conflict
from mapf.solvers._conflict_tree import (
    SearchContext,
    branch_constraints,
    termination_reason,
)
from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol
from mapf.solvers.validation import validated_solver


class CTNode:
    """Conflict Tree (CT) node for Conflict-Based Search."""

    def __init__(
        self,
        constraints: dict[str, set[tuple[Point, int]]],
        edge_constraints: dict[str, set[tuple[Point, Point, int]]],
        paths: dict[str, Path],
        cost: int,
    ) -> None:
        self.constraints = constraints
        self.edge_constraints = edge_constraints
        self.paths = paths
        self.cost = cost

    def __lt__(self, other: CTNode) -> bool:
        return self.cost < other.cost


class CentralizedCBSSolver(MAPFSolverProtocol):
    """Bounded Conflict-Based Search using action costs (Sharon et al., 2015).

    Search limits can prevent finding a solution or establishing optimality.
    Inspect termination diagnostics and validate returned paths independently."""

    def __init__(self, time_limit_sec: float = 10.0, max_iterations: int = 500) -> None:
        self._name = "CBS (Centralized Optimal)"
        self.time_limit_sec = time_limit_sec
        self.max_iterations = max_iterations

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_centralized(self) -> bool:
        return True

    def _replan_low_level(
        self,
        agent_id: str,
        instance: MAPFInstance,
        config: SimulationConfig,
        vertex_constraints: set[tuple[Point, int]],
        edge_constraints: set[tuple[Point, Point, int]],
    ) -> Path | None:
        """Low-level Space-Time A* search respecting CT node constraints."""
        res_table = ReservationTable()
        for pt, t in vertex_constraints:
            res_table.reserve_vertex("FORBIDDEN", pt, t)
        for u, v, t in edge_constraints:
            res_table.reserve_edge("FORBIDDEN", v, u, t)

        planner = SpaceTimeAStar(
            grid_width=instance.grid_width,
            grid_height=instance.grid_height,
            obstacles=instance.obstacles,
        )

        path = planner.search(
            start=instance.starts[agent_id],
            goal=instance.goals[agent_id],
            start_time=0,
            reservation_table=res_table,
            allow_wait=config.setting.allow_wait,
            max_time_steps=config.max_steps,
            max_expansions=config.max_astar_expansions,
            permanent_at_goal=not config.setting.disappear_at_target,
        )
        self._last_low_level_status = planner.last_search_status
        if planner.last_search_status in ("expansion_limit", "horizon_limit"):
            self._incomplete_low_level = True
        return path

    def _root(self, context: SearchContext, start_time: float) -> CTNode | MAPFSolution:
        instance, config = context.instance, context.config
        vertices: dict[str, set[tuple[Point, int]]] = {
            a: set() for a in instance.starts
        }
        edges: dict[str, set[tuple[Point, Point, int]]] = {
            a: set() for a in instance.starts
        }
        paths: dict[str, Path] = {}
        for agent in instance.starts:
            path = self._replan_low_level(
                agent, instance, config, vertices[agent], edges[agent]
            )
            if path is None:
                return MAPFSolution(
                    solver_name=self.name,
                    is_centralized=True,
                    success=False,
                    runtime_ms=(time.perf_counter() - start_time) * 1000.0,
                    metrics={
                        "termination_reason": "low_level_limit"
                        if self._incomplete_low_level
                        else "low_level_failed",
                        "low_level_status": self._last_low_level_status,
                        "timeout": False,
                    },
                )
            paths[agent] = path
        return CTNode(vertices, edges, paths, sum(p.length for p in paths.values()))

    def _children(
        self, parent: CTNode, conflict: Conflict, context: SearchContext
    ) -> Iterator[CTNode]:
        for agent in (conflict.agent_a, conflict.agent_b):
            vertices, edges = branch_constraints(
                parent.constraints, parent.edge_constraints, conflict, agent
            )
            if not context.admit(vertices, edges):
                continue
            path = self._replan_low_level(
                agent, context.instance, context.config, vertices[agent], edges[agent]
            )
            if path is not None:
                paths = dict(parent.paths)
                paths[agent] = path
                yield CTNode(
                    vertices, edges, paths, sum(p.length for p in paths.values())
                )

    def _solved(self, node: CTNode, start_time: float, iterations: int) -> MAPFSolution:
        return MAPFSolution(
            solver_name=self.name,
            is_centralized=True,
            success=True,
            paths=node.paths,
            makespan=max(p.length for p in node.paths.values()),
            sum_of_costs=node.cost,
            runtime_ms=(time.perf_counter() - start_time) * 1000.0,
            metrics={
                "cbs_iterations": iterations,
                "optimal": not self._incomplete_low_level,
                "optimality_scope": "within declared absorbing-goal MAPF semantics; no pruned bounded low-level branch",
                "low_level_incomplete": self._incomplete_low_level,
            },
        )

    @validated_solver
    def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution:
        start_time = time.perf_counter()
        self._incomplete_low_level = False
        self._last_low_level_status = "not_started"
        context = SearchContext(instance, config)
        root = self._root(context, start_time)
        if isinstance(root, MAPFSolution):
            return root
        counter = 0
        open_list: list[tuple[int, int, CTNode]] = [(root.cost, counter, root)]
        effective_timeout = (
            config.centralized_timeout_sec
            if "centralized_timeout_sec" in config.model_fields_set
            else self.time_limit_sec
        )
        iterations = 0
        timed_out = False
        while open_list and iterations < self.max_iterations:
            iterations += 1
            if time.perf_counter() - start_time > effective_timeout:
                timed_out = True
                break
            _, _, current = heapq.heappop(open_list)
            conflict = find_first_conflict(
                paths=current.paths,
                current_time=0,
                lookahead_steps=config.max_steps,
                disappear_at_target=config.setting.disappear_at_target,
            )
            if conflict is None:
                return self._solved(current, start_time, iterations)
            for child in self._children(current, conflict, context):
                counter += 1
                heapq.heappush(open_list, (child.cost, counter, child))
        return MAPFSolution(
            solver_name=self.name,
            is_centralized=True,
            success=False,
            runtime_ms=(time.perf_counter() - start_time) * 1000.0,
            metrics={
                "cbs_iterations": iterations,
                "timeout": timed_out,
                "low_level_incomplete": self._incomplete_low_level,
                "termination_reason": termination_reason(
                    timed_out, bool(open_list), self._incomplete_low_level
                ),
            },
        )
