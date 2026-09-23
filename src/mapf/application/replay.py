"""Build replay results from independent path assessment and recorded frames.

The timeline starts at t=0 and separates physical lifecycle state, recorded
local decisions and hindsight occupancy. Replay does not resume the solver.
"""

from __future__ import annotations

from typing import Any

from mapf.application._replay_assessment import assess_solution
from mapf.application._replay_frames import ReplayTimeline, TimelineSettings
from mapf.application.contracts import SolverRunResult
from mapf.core.models import SimulationSetting
from mapf.metrics.costs import trajectory_costs
from mapf.solvers.base import MAPFInstance, MAPFSolution

_METRIC_NAMES = (
    "negotiation_count",
    "successful_negotiations",
    "information_sharing_rate",
    "norm_path_diff",
)


def _measured_metrics(solution: MAPFSolution, costs: dict[str, Any]) -> dict[str, Any]:
    metrics = solution.metrics
    measured = {**costs, **metrics.get("communication", {})}
    for key in ("termination_reason", "solver_diagnostics"):
        if key in metrics:
            measured[key] = metrics[key]
    if "nego_by_step" in metrics:
        measured["negotiations_by_tick"] = {
            str(t): n for t, n in metrics["nego_by_step"].items()
        }
        measured["negotiation_count"] = metrics["negotiation_count"]
        measured["successful_negotiations"] = metrics["successful_negotiations"]
    return measured


def build_solver_run_result(
    solver_name: str,
    solver_key: str,
    instance: MAPFInstance,
    solution: MAPFSolution,
    setting: SimulationSetting,
    fov_size: int,
    initial_tokens: int = 5,
    max_steps: int = 100,
    include_frames: bool = True,
) -> SolverRunResult:
    """Verify a candidate, construct its timeline and report canonical action costs.

    ``solver_name`` is retained for API compatibility; the recorded solution names
    the actual solver. Presentation settings never alter candidate verification.
    """
    assessment = assess_solution(instance, solution, setting, max_steps)
    timeline = ReplayTimeline(
        instance,
        solution,
        assessment,
        TimelineSettings(setting, fov_size, initial_tokens, include_frames),
    )
    costs = trajectory_costs(instance, solution.paths)
    metrics = solution.metrics
    return SolverRunResult(
        solver=solution.solver_name,
        solver_key=solver_key,
        is_centralized=solution.is_centralized,
        status=assessment.status,
        success=assessment.success,
        solved_count=assessment.solved_count,
        total_agents=len(instance.starts),
        makespan=costs["action_makespan"]
        if assessment.success
        else timeline.total_ticks,
        sum_of_costs=costs["action_sum_of_costs"]
        if assessment.success
        else costs["recorded_action_count"],
        reported_makespan=metrics.get("solver_reported_makespan", solution.makespan),
        reported_sum_of_costs=metrics.get(
            "solver_reported_sum_of_costs", solution.sum_of_costs
        ),
        solver_outcome="solved"
        if metrics.get("solver_reported_success", solution.success)
        else "not_solved",
        validation=assessment.receipt,
        metric_availability={key: key in metrics for key in _METRIC_NAMES},
        runtime_ms=round(solution.runtime_ms, 2),
        negotiation_count=metrics.get("negotiation_count", 0),
        successful_negotiations=metrics.get("successful_negotiations", 0),
        information_sharing_rate=metrics.get("information_sharing_rate", 0.0),
        norm_path_diff=metrics.get("norm_path_diff", 0.0),
        instance_hash=solution.instance_hash,
        run_id=solution.run_id,
        paths=timeline.paths,
        frames=timeline.build(),
        measured_metrics=_measured_metrics(solution, costs),
    )
