"""Extension boundaries reject misleading solver claims using independent witnesses."""

from copy import deepcopy

import pytest

from mapf.conformance import check_solver
from mapf.core.hashing import compute_instance_hash
from mapf.core.models import Path, Point, SimulationConfig, SimulationSetting
from mapf.solvers.base import MAPFInstance, MAPFSolution


class FixtureSolver:
    name = "conformance-fixture"
    is_centralized = True

    def __init__(self, case):
        self.case = case

    def solve(self, instance, config):
        if self.case == "return-type":
            return {"success": True}
        if self.case == "mutation":
            instance.starts["a"] = Point(2, 1)
        points = [Point(0, 0), Point(1, 0), Point(2, 0)]
        if self.case == "incomplete-success":
            points = points[:2]
        if self.case == "physical-failure":
            points = [points[0], points[-1]]
        if self.case == "prefix":
            points = points[:2]
        return MAPFSolution(
            solver_name="different" if self.case == "identity" else self.name,
            is_centralized=True,
            instance_hash="stale" if self.case == "hash" else compute_instance_hash(instance, config.setting),
            success=self.case not in {"no-paths", "prefix", "physical-failure"},
            paths={} if self.case == "no-paths" else {"a": Path(points=points)},
            makespan=2, sum_of_costs=999 if self.case == "cost" else 2,
        )


@pytest.fixture
def scenario():
    instance = MAPFInstance(grid_width=3, grid_height=2, starts={"a": Point(0, 0)}, goals={"a": Point(2, 0)})
    config = SimulationConfig(grid_width=3, grid_height=2, setting=SimulationSetting.SETTING_4)
    return instance, config


@pytest.mark.parametrize(("case", "exception", "message"), [
    ("return-type", TypeError, "MAPFSolution"),
    ("mutation", ValueError, "mutated"),
    ("identity", ValueError, "identity mismatch"),
    ("hash", ValueError, "instance identity"),
    ("incomplete-success", ValueError, "independent path validation"),
    ("physical-failure", ValueError, "physical violations"),
    ("cost", ValueError, "canonical path costs"),
])
def test_invalid_extension_result_is_rejected_without_changing_caller_inputs(scenario, case, exception, message):
    instance, config = scenario
    before = deepcopy((instance.model_dump(), config.model_dump()))
    with pytest.raises(exception, match=message):
        check_solver(FixtureSolver(case), instance, config)
    assert (instance.model_dump(), config.model_dump()) == before


@pytest.mark.parametrize(("case", "status"), [("no-paths", "not_checked"), ("prefix", "valid_prefix"), ("valid", "valid_solution")])
def test_unsolved_prefix_and_complete_solution_have_different_claims(scenario, case, status):
    receipt = check_solver(FixtureSolver(case), *scenario)
    assert receipt["status"] == status
    assert receipt["success"] is (case == "valid")
    if case == "no-paths":
        assert receipt["costs"] is None
    else:
        assert receipt["costs"]["action_sum_of_costs"] == (None if case == "prefix" else 2)
        assert receipt["costs"]["recorded_action_count"] == (1 if case == "prefix" else 2)
