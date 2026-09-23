"""Independent examples for rejection order, diagnostic data and goal occupancy."""

import pytest

from mapf.core.models import Path, Point, SimulationSetting
from mapf.core.solution_validator import ValidationError, validate_solution
from mapf.solvers.base import MAPFInstance


def instance(**changes):
    values = {"grid_width": 4, "grid_height": 3, "starts": {"a": Point(0, 0)},
              "goals": {"a": Point(2, 0)}, "obstacles": {Point(1, 1)}}
    return MAPFInstance(**(values | changes))


@pytest.mark.parametrize(("points", "errors"), [
    ([], [("missing_path", None, None)]),
    ([(1, 0), (2, 0)], [("wrong_start", None, (1, 0))]),
    ([(0, 0), (1, 0)], [("wrong_goal", None, (1, 0))]),
    ([(0, 0), (2, 0)], [("teleport", 1, (2, 0))]),
    ([(0, 0), (1, 0), (1, 1), (2, 1), (2, 0)], [("obstacle", 2, (1, 1))]),
    ([(0, 0), (-1, 0), (0, 0), (1, 0), (2, 0)], [("out_of_bounds", 1, (-1, 0))]),
    ([(0, 0), (1, 0), (2, 0), (3, 0), (2, 0)], [("departure_after_goal", 3, (3, 0))]),
], ids=["missing", "start", "goal", "teleport", "obstacle", "bounds", "departure"])
def test_path_errors_identify_agent_tick_and_cell(points, errors):
    result = validate_solution(instance(), {"a": Path(points=[Point(*p) for p in points])},
                               SimulationSetting.SETTING_4)
    assert not result.is_valid
    assert result.error_count == len(errors)
    assert [(e.error_type, e.time_step, e.location) for e in result.errors] == errors
    assert all(e.agent_a == "a" and e.agent_b is None for e in result.errors)


def test_roster_errors_are_deterministic_and_do_not_drop_unknown_paths():
    result = validate_solution(instance(starts={}, goals={"b": Point(1, 0)}),
                               {"c": Path(points=[Point(2, 0)])},
                               SimulationSetting.SETTING_4)
    assert [(e.error_type, e.agent_a) for e in result.errors] == [
        ("empty_roster", ""), ("roster_mismatch", "b"), ("unknown_agent", "c")]
    mismatch = validate_solution(instance(goals={}), {}, SimulationSetting.SETTING_4)
    assert [(e.error_type, e.agent_a) for e in mismatch.errors] == [("roster_mismatch", "a")]


@pytest.mark.parametrize("setting", list(SimulationSetting))
def test_wait_rule_distinguishes_travel_from_goal_parking(setting):
    points = [Point(0, 0), Point(0, 0), Point(1, 0), Point(2, 0), Point(2, 0)]
    result = validate_solution(instance(), {"a": Path(points=points)}, setting)
    expected = [] if setting.allow_wait else [("illegal_wait", 1)]
    assert [(e.error_type, e.time_step) for e in result.errors] == expected


@pytest.mark.parametrize("setting", list(SimulationSetting))
def test_goal_removal_occurs_after_arrival_and_incomplete_paths_still_occupy(setting):
    scenario = instance(starts={"a": Point(0, 0), "b": Point(1, 1)},
                        goals={"a": Point(1, 0), "b": Point(0, 0)}, obstacles=set())
    paths = {"a": Path(points=[Point(0, 0), Point(1, 0)]),
             "b": Path(points=[Point(1, 1), Point(2, 1), Point(2, 0), Point(1, 0), Point(0, 0)])}
    result = validate_solution(scenario, paths, setting)
    assert result.is_valid == setting.disappear_at_target
    if not setting.disappear_at_target:
        assert [e.to_list() for e in result.errors] == [["vertex_collision", "a", "b", 3, [1, 0]]]
    scenario = scenario.model_copy(update={"goals": {"a": Point(3, 0), "b": Point(0, 0)}})
    result = validate_solution(scenario, paths, setting)
    assert [e.error_type for e in result.errors] == ["wrong_goal", "vertex_collision"]


def test_edge_swap_reports_departure_tick_and_both_agents():
    scenario = instance(starts={"a": Point(0, 0), "b": Point(1, 0)},
                        goals={"a": Point(1, 0), "b": Point(0, 0)})
    result = validate_solution(scenario, {"a": Path(points=[Point(0, 0), Point(1, 0)]),
                                         "b": Path(points=[Point(1, 0), Point(0, 0)])},
                               SimulationSetting.SETTING_4)
    assert [e.to_list() for e in result.errors] == [["edge_collision", "a", "b", 0, [1, 0]]]
    assert result.error_summary() == ["[edge_collision] agent=a, peer=b, t=0, loc=(1, 0)"]
    assert ValidationError("missing_path", "a").to_list() == ["missing_path", "a"]
