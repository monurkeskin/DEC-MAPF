from __future__ import annotations

import heapq
import time

from mapf.core.models import ConflictType, Path, Point, SimulationConfig
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar
from mapf.negotiation.conflict import find_first_conflict
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
    """Optimal Conflict-Based Search (CBS) algorithm (Sharon et al., 2015)."""

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

    @validated_solver
    def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution:
        start_time = time.perf_counter()
        self._incomplete_low_level = False
        self._last_low_level_status = "not_started"

        # 1. Root CT Node: Independent shortest paths
        root_constraints: dict[str, set[tuple[Point, int]]] = {
            a: set() for a in instance.starts
        }
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
                    metrics={"termination_reason": "low_level_limit" if self._incomplete_low_level else "low_level_failed",
                             "low_level_status": self._last_low_level_status, "timeout": False},
                )
            root_paths[a_id] = path

        root_cost = sum(p.length for p in root_paths.values())
        root_node = CTNode(
            root_constraints, root_edge_constraints, root_paths, root_cost
        )

        # High-level open list
        counter = 0
        open_list: list[tuple[int, int, CTNode]] = [(root_cost, counter, root_node)]

        effective_timeout = (
            config.centralized_timeout_sec
            if "centralized_timeout_sec" in config.model_fields_set
            else self.time_limit_sec
        )

        iterations = 0
        timed_out = False
        seen_constraints: set[object] = set()
        while open_list and iterations < self.max_iterations:
            iterations += 1
            if time.perf_counter() - start_time > effective_timeout:
                timed_out = True
                break

            _, _, current_node = heapq.heappop(open_list)

            # Check for conflict
            conflict = find_first_conflict(
                paths=current_node.paths,
                current_time=0,
                lookahead_steps=config.max_steps,
                disappear_at_target=config.setting.disappear_at_target,
            )

            if conflict is None:
                # Goal node found! Optimal conflict-free paths
                runtime_ms = (time.perf_counter() - start_time) * 1000.0
                makespan = max(p.length for p in current_node.paths.values())
                sum_of_costs = current_node.cost

                return MAPFSolution(
                    solver_name=self.name,
                    is_centralized=True,
                    success=True,
                    paths=current_node.paths,
                    makespan=makespan,
                    sum_of_costs=sum_of_costs,
                    runtime_ms=runtime_ms,
                    metrics={"cbs_iterations": iterations, "optimal": not self._incomplete_low_level,
                             "optimality_scope": "within declared absorbing-goal MAPF semantics; no pruned bounded low-level branch",
                             "low_level_incomplete": self._incomplete_low_level},
                )

            # Branch on conflict
            conflicting_agents = [conflict.agent_a, conflict.agent_b]
            for a_id in conflicting_agents:
                new_constraints = {
                    a: set(current_node.constraints[a])
                    for a in current_node.constraints
                }
                new_edge_constraints = {
                    a: set(current_node.edge_constraints[a])
                    for a in current_node.edge_constraints
                }

                if conflict.conflict_type == ConflictType.VERTEX:
                    new_constraints[a_id].add((conflict.location_a, conflict.time))
                else:
                    # Edge swap conflict: agent cannot traverse in its conflicting direction at conflict.time
                    loc_from = (
                        conflict.location_a
                        if a_id == conflict.agent_a
                        else (conflict.location_b or conflict.location_a)
                    )
                    loc_to = (
                        (conflict.location_b or conflict.location_a)
                        if a_id == conflict.agent_a
                        else conflict.location_a
                    )
                    new_edge_constraints[a_id].add((loc_from, loc_to, conflict.time))

                signature = tuple((a, frozenset(new_constraints[a]), frozenset(new_edge_constraints[a]))
                                  for a in sorted(new_constraints))
                if signature in seen_constraints:
                    continue
                seen_constraints.add(signature)

                # Replan low-level for this agent
                new_path = self._replan_low_level(
                    agent_id=a_id,
                    instance=instance,
                    config=config,
                    vertex_constraints=new_constraints[a_id],
                    edge_constraints=new_edge_constraints[a_id],
                )

                if new_path is not None:
                    new_paths = dict(current_node.paths)
                    new_paths[a_id] = new_path
                    new_cost = sum(p.length for p in new_paths.values())
                    new_node = CTNode(
                        constraints=new_constraints,
                        edge_constraints=new_edge_constraints,
                        paths=new_paths,
                        cost=new_cost,
                    )
                    counter += 1
                    heapq.heappush(open_list, (new_cost, counter, new_node))

        runtime_ms = (time.perf_counter() - start_time) * 1000.0
        return MAPFSolution(
            solver_name=self.name,
            is_centralized=True,
            success=False,
            runtime_ms=runtime_ms,
            metrics={"cbs_iterations": iterations, "timeout": timed_out,
                     "low_level_incomplete": self._incomplete_low_level,
                     "termination_reason": "timeout" if timed_out else "iteration_limit" if open_list
                     else "low_level_limit" if self._incomplete_low_level else "search_exhausted"},
        )
