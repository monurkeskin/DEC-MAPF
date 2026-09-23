"""Independent candidate assessment shared by replay and checked imports."""

from dataclasses import asdict, dataclass
from typing import Literal

from mapf.application.contracts import ValidationReceipt
from mapf.core.models import SimulationSetting
from mapf.core.solution_validator import (
    ValidationError,
    ValidationResult,
    validate_solution,
)
from mapf.solvers.base import MAPFInstance, MAPFSolution

RunStatus = Literal["solved", "failed", "truncated", "invalid"]


@dataclass(frozen=True)
class SolutionAssessment:
    """Separate reported completion, physical violations and first goal arrivals."""

    status: RunStatus
    arrival_ticks: dict[str, int | None]
    physical_errors: list[ValidationError]
    receipt: ValidationReceipt

    @property
    def success(self) -> bool:
        return self.status == "solved"

    @property
    def solved_count(self) -> int:
        return sum(tick is not None for tick in self.arrival_ticks.values())


def goal_arrivals(instance: MAPFInstance, solution: MAPFSolution) -> dict[str, int | None]:
    arrivals: dict[str, int | None] = {}
    for aid, goal in instance.goals.items():
        path = solution.paths.get(aid)
        points = path.points if path else []
        arrivals[aid] = next((t for t, point in enumerate(points) if point == goal), None)
    return arrivals


def _physical_errors(validation: ValidationResult, incomplete: bool) -> list[ValidationError]:
    ignored = {"wrong_goal", "missing_path"} if incomplete else {"wrong_goal"}
    return [error for error in validation.errors if error.error_type not in ignored]


def _receipt(validation: ValidationResult, errors: list[ValidationError],
             incomplete: bool) -> ValidationReceipt:
    status: Literal["valid_solution", "valid_prefix", "invalid", "not_checked"]
    if errors:
        status = "invalid"
    elif incomplete:
        status = "not_checked"
    else:
        status = "valid_solution" if validation.is_valid else "valid_prefix"
    return ValidationReceipt(
        status=status, is_valid=validation.is_valid, prefix_valid=not errors and not incomplete,
        errors=[asdict(error) for error in validation.errors],
        first_violation_tick=min((error.time_step or 0 for error in errors), default=None),
    )


def _status(solution: MAPFSolution, receipt: ValidationReceipt, max_steps: int) -> RunStatus:
    if receipt.status == "invalid":
        return "invalid"
    if receipt.is_valid and solution.success:
        return "solved"
    return "truncated" if solution.makespan >= max_steps else "failed"


def assess_solution(instance: MAPFInstance, solution: MAPFSolution,
                    setting: SimulationSetting, max_steps: int) -> SolutionAssessment:
    validation = validate_solution(instance, solution.paths, setting)
    has_roster = set(solution.paths) == set(instance.starts)
    reported_success = solution.metrics.get("solver_reported_success", solution.success)
    incomplete = solution.is_centralized and not reported_success and not has_roster
    errors = _physical_errors(validation, incomplete)
    receipt = _receipt(validation, errors, incomplete)
    return SolutionAssessment(_status(solution, receipt, max_steps),
                              goal_arrivals(instance, solution), errors, receipt)
