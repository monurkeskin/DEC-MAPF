"""Shared input contract and independent output gate for built-in solver entry points."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from functools import wraps
from typing import Any

from mapf.core.hashing import compute_instance_hash
from mapf.core.models import SimulationConfig
from mapf.core.solution_validator import validate_solution
from mapf.metrics.costs import trajectory_costs
from mapf.solvers.base import MAPFInstance, MAPFSolution


def validated_solver(
    method: Callable[[Any, MAPFInstance, SimulationConfig], MAPFSolution],
) -> Callable[[Any, MAPFInstance, SimulationConfig], MAPFSolution]:
    @wraps(method)
    def solve(
        self: Any, instance: MAPFInstance, config: SimulationConfig
    ) -> MAPFSolution:
        if not instance.starts or instance.starts.keys() != instance.goals.keys():
            raise ValueError("A solver requires a nonempty matching start/goal roster")
        if len(set(instance.starts.values())) != len(instance.starts):
            raise ValueError("Starting positions must be unique")
        if not config.setting.disappear_at_target and len(
            set(instance.goals.values())
        ) != len(instance.goals):
            raise ValueError("Shared goals cannot remain occupied indefinitely")
        for p in list(instance.starts.values()) + list(instance.goals.values()):
            if (
                not (0 <= p.x < instance.grid_width and 0 <= p.y < instance.grid_height)
                or p in instance.obstacles
            ):
                raise ValueError("Start or goal is outside the traversable grid")
        for key in ("grid_width", "grid_height", "obstacles"):
            if key in config.model_fields_set and getattr(config, key) != getattr(
                instance, key
            ):
                raise ValueError(f"Instance/config geometry mismatch: {key}")
        config = config.model_copy(
            update={
                k: getattr(instance, k)
                for k in ("grid_width", "grid_height", "obstacles")
            }
        )
        solution = method(self, instance, config)
        check = validate_solution(instance, solution.paths, config.setting)
        costs = trajectory_costs(instance, solution.paths)
        return solution.model_copy(
            update={
                "success": solution.success and check.is_valid,
                "instance_hash": compute_instance_hash(instance, config.setting),
                "sum_of_costs": costs["action_sum_of_costs"] if check.is_valid else solution.sum_of_costs,
                "makespan": costs["action_makespan"] if check.is_valid else solution.makespan,
                "metrics": dict(
                    solution.metrics,
                    cost_metrics=costs,
                    norm_path_diff=costs["individual_detour_ratio"] or 0.0,
                    solver_reported_success=solution.success,
                    solver_reported_sum_of_costs=solution.sum_of_costs,
                    solver_reported_makespan=solution.makespan,
                    independent_validation={
                        "version": "trajectory-v2",
                        "is_valid": check.is_valid,
                        "errors": [asdict(e) for e in check.errors],
                    },
                ),
            }
        )

    return solve
