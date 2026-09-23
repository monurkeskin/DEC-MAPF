from __future__ import annotations

import heapq
import time
from collections.abc import Iterator
from dataclasses import dataclass

from mapf.core.models import Conflict, Path, Point, SimulationConfig
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar
from mapf.negotiation.conflict import detect_conflicts, find_first_conflict
from mapf.solvers._conflict_tree import (
    EdgeConstraints,
    SearchContext,
    VertexConstraints,
    branch_constraints,
    termination_reason,
)
from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol
from mapf.solvers.validation import validated_solver


@dataclass(eq=False)
class EECBSNode:
    """High-level node for the simplified focal solver; costs count actions."""

    node_id: int
    constraints: VertexConstraints
    edge_constraints: EdgeConstraints
    paths: dict[str, Path]
    cost: int
    num_conflicts: int = 0

    def __lt__(self, other: EECBSNode) -> bool:
        # Tie breaking: prefer fewer conflicts, then lower cost, then node_id
        if self.cost != other.cost:
            return self.cost < other.cost
        if self.num_conflicts != other.num_conflicts:
            return self.num_conflicts < other.num_conflicts
        return self.node_id < other.node_id


class CentralizedEECBSSolver(MAPFSolverProtocol):
    """Simplified Python focal CBS, kept under its legacy public class name.

    This implementation is not the reference EECBS algorithm. Its weight is a
    search parameter; a formal suboptimality guarantee has not been established.
    """

    def __init__(
        self,
        suboptimality: float = 1.1,
        time_limit_sec: float = 10.0,
        max_iterations: int = 1500,
    ) -> None:
        self.suboptimality = max(1.0, float(suboptimality))
        sub_str = f"{self.suboptimality:.1f}"
        self._name = f"SimplifiedFocalCBS-{sub_str} (legacy EECBS)"
        self.time_limit_sec = time_limit_sec
        self.max_iterations = max_iterations
        self._node_counter = 0

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
        """Low-level Space-Time A* search respecting node constraints."""
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

    def _new_node(
        self,
        vertices: VertexConstraints,
        edges: EdgeConstraints,
        paths: dict[str, Path],
        config: SimulationConfig,
    ) -> EECBSNode:
        conflicts = detect_conflicts(
            paths,
            lookahead_steps=config.max_steps,
            disappear_at_target=config.setting.disappear_at_target,
        )
        self._node_counter += 1
        return EECBSNode(
            self._node_counter,
            vertices,
            edges,
            paths,
            sum(p.length for p in paths.values()),
            len(conflicts),
        )

    def _root(
        self, context: SearchContext, start_time: float
    ) -> EECBSNode | MAPFSolution:
        instance, config = context.instance, context.config
        vertices: VertexConstraints = {a: set() for a in instance.starts}
        edges: EdgeConstraints = {a: set() for a in instance.starts}
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
                        "error": f"Root search did not return a path for agent {agent}.",
                        "termination_reason": "low_level_limit"
                        if self._incomplete_low_level
                        else "low_level_failed",
                        "low_level_status": self._last_low_level_status,
                        "timeout": False,
                    },
                )
            paths[agent] = path
        return self._new_node(vertices, edges, paths, config)

    def _children(
        self, parent: EECBSNode, conflict: Conflict, context: SearchContext
    ) -> Iterator[EECBSNode]:
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
                yield self._new_node(vertices, edges, paths, context.config)

    def _select(self, open_list: list[EECBSNode]) -> EECBSNode:
        focal_bound = self.suboptimality * float(open_list[0].cost)
        candidates = [n for n in open_list if float(n.cost) <= focal_bound]
        if not candidates:
            return heapq.heappop(open_list)
        best = min(candidates, key=lambda n: (n.num_conflicts, n.cost))
        open_list.remove(best)
        heapq.heapify(open_list)
        return best

    def _solved(
        self, node: EECBSNode, start_time: float, iterations: int
    ) -> MAPFSolution:
        return MAPFSolution(
            solver_name=self.name,
            is_centralized=True,
            success=True,
            paths=node.paths,
            makespan=max((p.length for p in node.paths.values()), default=0),
            sum_of_costs=node.cost,
            runtime_ms=(time.perf_counter() - start_time) * 1000.0,
            metrics={"iterations": iterations, "suboptimality": self.suboptimality},
        )

    @validated_solver
    def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution:
        start_time = time.perf_counter()
        self._node_counter = 0
        self._incomplete_low_level = False
        self._last_low_level_status = "not_started"
        context = SearchContext(instance, config)
        root = self._root(context, start_time)
        if isinstance(root, MAPFSolution):
            return root
        if not root.num_conflicts:
            return self._solved(root, start_time, 1)
        open_list = [root]
        heapq.heapify(open_list)
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
            current = self._select(open_list)
            conflict = find_first_conflict(
                current.paths,
                lookahead_steps=config.max_steps,
                disappear_at_target=config.setting.disappear_at_target,
            )
            if conflict is None:
                return self._solved(current, start_time, iterations)
            for child in self._children(current, conflict, context):
                heapq.heappush(open_list, child)
        return MAPFSolution(
            solver_name=self.name,
            is_centralized=True,
            success=False,
            runtime_ms=(time.perf_counter() - start_time) * 1000.0,
            metrics={
                "iterations": iterations,
                "timeout": timed_out,
                "low_level_incomplete": self._incomplete_low_level,
                "termination_reason": termination_reason(
                    timed_out, bool(open_list), self._incomplete_low_level
                ),
            },
        )
