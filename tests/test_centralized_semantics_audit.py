"""Setting, objective, and failure witnesses independent of central solver internals."""

import pytest

from mapf.application.replay import build_solver_run_result
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.solvers.base import MAPFInstance, MAPFSolution
from mapf.solvers.cbs import CentralizedCBSSolver
from mapf.solvers.eecbs import CentralizedEECBSSolver


@pytest.mark.parametrize("weight", [1.0, 1.1, 1.5])
def test_focal_objective_and_raw_report_count_actions_not_vertices(weight):
    instance = MAPFInstance(grid_width=3, grid_height=1,
        starts={"a": Point(0, 0)}, goals={"a": Point(2, 0)})
    result = CentralizedEECBSSolver(suboptimality=weight).solve(instance, SimulationConfig())
    assert result.success
    assert result.metrics["solver_reported_sum_of_costs"] == 2
    assert result.metrics["solver_reported_makespan"] == 2


@pytest.mark.parametrize("solver_type", [CentralizedCBSSolver, CentralizedEECBSSolver])
def test_iteration_exhaustion_is_not_a_wall_clock_timeout(solver_type):
    instance = MAPFInstance(grid_width=3, grid_height=2,
        starts={"a": Point(0, 0), "b": Point(2, 0)},
        goals={"a": Point(2, 0), "b": Point(0, 0)})
    result = solver_type(max_iterations=0).solve(instance, SimulationConfig())
    assert not result.success
    assert result.metrics["termination_reason"] == "iteration_limit"
    assert result.metrics["timeout"] is False


@pytest.mark.parametrize("solver_type", [CentralizedCBSSolver, CentralizedEECBSSolver])
def test_root_horizon_failure_does_not_prove_infeasibility(solver_type):
    instance = MAPFInstance(grid_width=5, grid_height=1,
        starts={"a": Point(0, 0)}, goals={"a": Point(4, 0)})
    result = solver_type().solve(instance, SimulationConfig(max_steps=2))
    assert not result.success
    assert result.metrics["termination_reason"] == "low_level_limit"
    assert result.metrics["low_level_status"] == "horizon_limit"


@pytest.mark.parametrize("claimed_success", [False, True])
def test_no_central_candidate_is_distinct_from_a_claimed_invalid_solution(claimed_success):
    instance = MAPFInstance(grid_width=3, grid_height=1,
        starts={"a": Point(0, 0)}, goals={"a": Point(2, 0)})
    solution = MAPFSolution(solver_name="fixture", is_centralized=True,
        success=claimed_success, metrics={"termination_reason": "iteration_limit"})
    result = build_solver_run_result("fixture", "CBS", instance, solution,
        SimulationSetting.SETTING_4, 5)
    assert result.status == ("invalid" if claimed_success else "failed")
    assert result.validation.status == ("invalid" if claimed_success else "not_checked")
    assert not result.validation.prefix_valid


@pytest.mark.parametrize("solver_type", [CentralizedCBSSolver, CentralizedEECBSSolver])
@pytest.mark.parametrize("setting", list(SimulationSetting))
def test_disappearing_agent_frees_its_goal_but_parked_agent_does_not(solver_type, setting):
    # A starts at its own goal in the only corridor. B cannot pass a parked A.
    instance = MAPFInstance(grid_width=3, grid_height=1,
        starts={"a": Point(1, 0), "b": Point(0, 0)},
        goals={"a": Point(1, 0), "b": Point(2, 0)})
    result = solver_type(max_iterations=30).solve(instance,
        SimulationConfig(setting=setting, max_steps=8))
    assert result.success == setting.disappear_at_target
    if result.success:
        assert result.sum_of_costs == 2
        assert result.paths["a"].length == 0
