from __future__ import annotations

import time

from mapf.core.models import Path, SimulationConfig
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar
from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol
from mapf.solvers.validation import validated_solver


class CentralizedPrioritizedSolver(MAPFSolverProtocol):
    """Centralized Prioritized Planning heuristic solver."""

    def __init__(self) -> None:
        self._name = "Prioritized Planning (Centralized Heuristic)"

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_centralized(self) -> bool:
        return True

    @validated_solver
    def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution:
        start_time = time.perf_counter()
        res_table = ReservationTable()
        paths: dict[str, Path] = {}

        planner = SpaceTimeAStar(
            grid_width=instance.grid_width,
            grid_height=instance.grid_height,
            obstacles=instance.obstacles,
        )

        # Prioritize agents with longer distances first
        agent_ids = sorted(
            instance.starts.keys(),
            key=lambda a: instance.starts[a].manhattan_distance(instance.goals[a]),
            reverse=True,
        )

        permanent = not config.setting.disappear_at_target

        for a_id in agent_ids:
            path = planner.search(
                start=instance.starts[a_id],
                goal=instance.goals[a_id],
                start_time=0,
                reservation_table=res_table,
                allow_wait=config.setting.allow_wait,
                max_time_steps=config.max_steps,
                max_expansions=config.max_astar_expansions,
                permanent_at_goal=permanent,
            )

            if path is None:
                # Prioritized planning failed to find path for lower priority agent
                return MAPFSolution(
                    solver_name=self.name,
                    is_centralized=True,
                    success=False,
                    paths=paths,
                    runtime_ms=(time.perf_counter() - start_time) * 1000.0,
                    metrics={"termination_reason": "low_level_limit" if planner.last_search_status in (
                        "expansion_limit", "horizon_limit") else "priority_order_failed",
                        "low_level_status": planner.last_search_status, "failed_agent": a_id},
                )

            paths[a_id] = path
            # Reserve in table (with permanent reservation if not disappearing at target)
            res_table.reserve_path(
                agent_id=a_id, path=path, start_time=0, permanent=permanent
            )

        from mapf.core.solution_validator import validate_solution

        val_result = validate_solution(instance, paths, config.setting)

        runtime_ms = (time.perf_counter() - start_time) * 1000.0
        makespan = max(p.length for p in paths.values()) if paths else 0
        sum_of_costs = sum(p.length for p in paths.values()) if paths else 0

        return MAPFSolution(
            solver_name=self.name,
            is_centralized=True,
            success=val_result.is_valid,
            paths=paths,
            makespan=makespan,
            sum_of_costs=sum_of_costs,
            runtime_ms=runtime_ms,
        )
