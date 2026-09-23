"""Concrete trajectories witness the assumptions displayed before a run."""
import pytest

from mapf.application.plans import preview
from mapf.application.presets import preset_request
from mapf.core.models import Path, Point, SimulationSetting
from mapf.core.solution_validator import validate_solution
from mapf.metrics.costs import trajectory_costs
from mapf.solvers.base import MAPFInstance


@pytest.mark.parametrize("setting", list(SimulationSetting))
def test_preview_wait_policy_agrees_with_independent_validation(setting):
    plan = preview(preset_request("interactive-v1", scenario_id="crossing-2a", setting=setting.name))
    assumptions = plan["semantics"]
    instance = MAPFInstance(grid_width=2, grid_height=1, starts={"a": Point(0, 0)}, goals={"a": Point(1, 0)})
    path = Path([Point(0, 0), Point(0, 0), Point(1, 0)])
    valid = validate_solution(instance, {"a": path}, setting).is_valid
    assert valid == assumptions["wait_before_goal"]
    assert assumptions["time_origin"] == "Initial positions are t=0; one transition consumes one tick."


@pytest.mark.parametrize("setting", list(SimulationSetting))
def test_goal_policy_explains_sequential_use_of_a_shared_goal(setting):
    instance = MAPFInstance(grid_width=3, grid_height=1,
                           starts={"a": Point(1, 0), "b": Point(0, 0)},
                           goals={"a": Point(2, 0), "b": Point(2, 0)})
    paths = {"a": Path([Point(1, 0), Point(2, 0)]),
             "b": Path([Point(0, 0), Point(1, 0), Point(2, 0)])}
    plan = preview(preset_request("interactive-v1", scenario_id="crossing-2a", setting=setting.name))
    assert validate_solution(instance, paths, setting).is_valid == (plan["semantics"]["goal_policy"] == "disappear")
    assert trajectory_costs(instance, paths)["action_sum_of_costs"] == 3


def test_edge_swap_is_forbidden_even_with_distinct_goals_and_waiting_enabled():
    instance = MAPFInstance(grid_width=2, grid_height=1,
                           starts={"a": Point(0, 0), "b": Point(1, 0)},
                           goals={"a": Point(1, 0), "b": Point(0, 0)})
    paths = {a: Path([instance.starts[a], instance.goals[a]]) for a in instance.starts}
    errors = validate_solution(instance, paths, SimulationSetting.SETTING_4)
    assert not errors.is_valid
    assert any("edge" in error.error_type for error in errors.errors)


def test_initial_goal_has_zero_cost():
    instance = MAPFInstance(grid_width=2, grid_height=1, starts={"a": Point(0, 0)}, goals={"a": Point(0, 0)})
    assert trajectory_costs(instance, {"a": Path([Point(0, 0)])})["action_sum_of_costs"] == 0
