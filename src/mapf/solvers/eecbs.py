from __future__ import annotations

import heapq
import time

from mapf.core.models import ConflictType, Path, Point, SimulationConfig
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar
from mapf.negotiation.conflict import detect_conflicts, find_first_conflict
from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol
from mapf.solvers.validation import validated_solver


class EECBSNode:
    """High-level node for the simplified focal solver; costs count actions."""

    def __init__(
        self,
        node_id: int,
        constraints: dict[str, set[tuple[Point, int]]],
        edge_constraints: dict[str, set[tuple[Point, Point, int]]],
        paths: dict[str, Path],
        cost: int,
        num_conflicts: int = 0,
    ) -> None:
        self.node_id = node_id
        self.constraints = constraints
        self.edge_constraints = edge_constraints
        self.paths = paths
        self.cost = cost
        self.num_conflicts = num_conflicts

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

    @validated_solver
    def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution:
        start_time = time.perf_counter()
        self._node_counter = 0
        self._incomplete_low_level = False
        self._last_low_level_status = "not_started"

        # 1. Root Node: Independent individual paths
        root_constraints: dict[str, set[tuple[Point, int]]] = {
            a: set() for a in instance.starts
        }
        seen_constraints: set[object] = set()
        root_edge_constraints: dict[str, set[tuple[Point, Point, int]]] = {
            a: set() for a in instance.starts
        }
        root_paths: dict[str, Path] = {}

        for a_id in instance.starts:
            path = self._replan_low_level(
                agent_id=a_id,
                instance=instance,
                config=config,
                vertex_constraints=root_constraints[a_id],
                edge_constraints=root_edge_constraints[a_id],
            )
            if path is None:
                return MAPFSolution(
                    solver_name=self.name,
                    is_centralized=True,
                    success=False,
                    runtime_ms=(time.perf_counter() - start_time) * 1000.0,
                    metrics={
                        "error": f"Root search did not return a path for agent {a_id}.",
                        "termination_reason": "low_level_limit" if self._incomplete_low_level else "low_level_failed",
                        "low_level_status": self._last_low_level_status, "timeout": False,
                    },
                )
            root_paths[a_id] = path

        root_cost = sum(p.length for p in root_paths.values())
        root_conflicts = detect_conflicts(
            root_paths,
            lookahead_steps=config.max_steps,
            disappear_at_target=config.setting.disappear_at_target,
        )

        self._node_counter += 1
        root_node = EECBSNode(
            node_id=self._node_counter,
            constraints=root_constraints,
            edge_constraints=root_edge_constraints,
            paths=root_paths,
            cost=root_cost,
            num_conflicts=len(root_conflicts),
        )

        if not root_conflicts:
            # Trivial root is conflict-free
            runtime = (time.perf_counter() - start_time) * 1000.0
            makespan = max((p.length for p in root_paths.values()), default=0)
            return MAPFSolution(
                solver_name=self.name,
                is_centralized=True,
                success=True,
                paths=root_paths,
                makespan=makespan,
                sum_of_costs=root_cost,
                runtime_ms=runtime,
                metrics={"iterations": 1, "suboptimality": self.suboptimality},
            )

        # OPEN: Min-heap sorted by node.cost
        open_list: list[EECBSNode] = [root_node]
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

            # Bounded focal list: nodes with cost <= w * f_min
            f_min = open_list[0].cost
            focal_bound = self.suboptimality * float(f_min)

            # In FOCAL, pick node with minimum num_conflicts
            focal_candidates = [n for n in open_list if float(n.cost) <= focal_bound]
            if not focal_candidates:
                best_node = heapq.heappop(open_list)
            else:
                best_node = min(
                    focal_candidates, key=lambda n: (n.num_conflicts, n.cost)
                )
                open_list.remove(best_node)
                heapq.heapify(open_list)

            # Check if this node is conflict-free
            first_conflict = find_first_conflict(
                best_node.paths,
                lookahead_steps=config.max_steps,
                disappear_at_target=config.setting.disappear_at_target,
            )

            if first_conflict is None:
                # Conflict-free candidate; independent validation follows at the solver boundary.
                runtime = (time.perf_counter() - start_time) * 1000.0
                makespan = max(
                    (p.length for p in best_node.paths.values()), default=0
                )
                return MAPFSolution(
                    solver_name=self.name,
                    is_centralized=True,
                    success=True,
                    paths=best_node.paths,
                    makespan=makespan,
                    sum_of_costs=best_node.cost,
                    runtime_ms=runtime,
                    metrics={
                        "iterations": iterations,
                        "suboptimality": self.suboptimality,
                    },
                )

            # Branching on first conflict: two children
            c = first_conflict
            branch_agents = [c.agent_a, c.agent_b]

            for constrained_agent in branch_agents:
                child_constraints = {
                    a: set(con) for a, con in best_node.constraints.items()
                }
                child_edge_constraints = {
                    a: set(con) for a, con in best_node.edge_constraints.items()
                }

                if c.conflict_type == ConflictType.VERTEX:
                    child_constraints[constrained_agent].add((c.location_a, c.time))
                elif c.conflict_type == ConflictType.EDGE:
                    loc_from = (
                        c.location_a
                        if constrained_agent == c.agent_a
                        else (c.location_b or c.location_a)
                    )
                    loc_to = (
                        (c.location_b or c.location_a)
                        if constrained_agent == c.agent_a
                        else c.location_a
                    )
                    child_edge_constraints[constrained_agent].add(
                        (loc_from, loc_to, c.time)
                    )

                signature = tuple((a, frozenset(child_constraints[a]), frozenset(child_edge_constraints[a]))
                                  for a in sorted(child_constraints))
                if signature in seen_constraints:
                    continue
                seen_constraints.add(signature)

                # Replan for the constrained agent
                new_path = self._replan_low_level(
                    agent_id=constrained_agent,
                    instance=instance,
                    config=config,
                    vertex_constraints=child_constraints[constrained_agent],
                    edge_constraints=child_edge_constraints[constrained_agent],
                )

                if new_path is not None:
                    child_paths = dict(best_node.paths)
                    child_paths[constrained_agent] = new_path
                    child_cost = sum(p.length for p in child_paths.values())
                    child_conflicts = detect_conflicts(
                        child_paths,
                        lookahead_steps=config.max_steps,
                        disappear_at_target=config.setting.disappear_at_target,
                    )

                    self._node_counter += 1
                    child_node = EECBSNode(
                        node_id=self._node_counter,
                        constraints=child_constraints,
                        edge_constraints=child_edge_constraints,
                        paths=child_paths,
                        cost=child_cost,
                        num_conflicts=len(child_conflicts),
                    )
                    heapq.heappush(open_list, child_node)

        # Timeout or exceeded iterations
        runtime = (time.perf_counter() - start_time) * 1000.0
        return MAPFSolution(
            solver_name=self.name,
            is_centralized=True,
            success=False,
            runtime_ms=runtime,
            metrics={
                "iterations": iterations,
                "timeout": timed_out,
                "low_level_incomplete": self._incomplete_low_level,
                "termination_reason": "timeout" if timed_out else "iteration_limit" if open_list
                else "low_level_limit" if self._incomplete_low_level else "search_exhausted",
            },
        )
