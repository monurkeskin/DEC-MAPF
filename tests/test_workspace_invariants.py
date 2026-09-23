"""Independent, hand-calculated cases for input, replay and solver boundaries."""

from itertools import permutations

import pytest

from mapf.application.scenarios import ScenarioService
from mapf.core.models import Path, Point, SimulationConfig, SimulationSetting
from mapf.core.solution_validator import validate_solution
from mapf.gui.frame_builder import build_solver_run_result
from mapf.solvers.base import MAPFInstance, MAPFSolution
from mapf.solvers.cbs import CentralizedCBSSolver
from mapf.solvers.eecbs import CentralizedEECBSSolver
from mapf.solvers.prioritized import CentralizedPrioritizedSolver
from tests.joint_state_oracle import assert_physical_paths, optimal_joint_cost


def test_unknown_agent_is_not_a_valid_solution():
    instance = MAPFInstance(
        grid_width=3, grid_height=3, starts={"a": Point(0, 0)}, goals={"a": Point(1, 0)}
    )
    paths = {
        "a": Path(points=[Point(0, 0), Point(1, 0)]),
        "ghost": Path(points=[Point(2, 2)]),
    }
    assert not validate_solution(instance, paths, SimulationSetting.SETTING_4).is_valid


def test_disappearing_agent_cannot_leave_its_goal():
    instance = MAPFInstance(
        grid_width=3, grid_height=3, starts={"a": Point(0, 0)}, goals={"a": Point(1, 0)}
    )
    path = Path(points=[Point(0, 0), Point(1, 0), Point(2, 0), Point(1, 0)])
    assert not validate_solution(
        instance, {"a": path}, SimulationSetting.SETTING_4
    ).is_valid


def test_scenario_requires_matching_nonempty_roster():
    empty = MAPFInstance(grid_width=3, grid_height=3, starts={}, goals={})
    missing = MAPFInstance(
        grid_width=3, grid_height=3, starts={"a": Point(0, 0)}, goals={}
    )
    assert ScenarioService.validate_instance(empty)
    assert ScenarioService.validate_instance(missing)


def test_wrong_start_cannot_be_reported_as_physical_validity():
    instance = MAPFInstance(
        grid_width=3, grid_height=3, starts={"a": Point(0, 0)}, goals={"a": Point(2, 0)}
    )
    sol = MAPFSolution(
        solver_name="fixture",
        is_centralized=True,
        success=True,
        paths={"a": Path(points=[Point(1, 0), Point(2, 0)])},
        makespan=1,
    )
    result = build_solver_run_result(
        "fixture", "fixture", instance, sol, SimulationSetting.SETTING_4, 3
    )
    assert result.status == "invalid"
    assert not result.success


def test_validator_indexes_preserve_incomplete_agent_occupancy():
    # A short unfinished trace is not a disappearance; B hits A at tick 2.
    instance = MAPFInstance(
        grid_width=3,
        grid_height=2,
        starts={"a": Point(1, 0), "b": Point(2, 1)},
        goals={"a": Point(0, 0), "b": Point(1, 0)},
    )
    paths = {
        "a": Path(points=[Point(1, 0)]),
        "b": Path(points=[Point(2, 1), Point(2, 0), Point(1, 0)]),
    }
    check = validate_solution(instance, paths, SimulationSetting.SETTING_4)
    assert any(
        e.error_type == "vertex_collision" and e.time_step == 2 for e in check.errors
    )


def test_replay_cost_comes_from_paths_not_solver_claim():
    instance = MAPFInstance(
        grid_width=3, grid_height=2, starts={"a": Point(0, 0)}, goals={"a": Point(2, 0)}
    )
    sol = MAPFSolution(
        solver_name="fixture",
        is_centralized=True,
        success=True,
        paths={"a": Path(points=[Point(0, 0), Point(1, 0), Point(2, 0)])},
        makespan=77,
        sum_of_costs=999,
    )
    result = build_solver_run_result(
        "fixture", "fixture", instance, sol, SimulationSetting.SETTING_4, 3
    )
    assert result.makespan == result.sum_of_costs == 2
    assert result.reported_makespan == 77 and result.reported_sum_of_costs == 999


def test_python_javascript_number_roundtrip_hash():
    import json
    import subprocess

    from mapf.application.runs import digest

    source = {"one": 1.0, "tiny": 0.000001, "zero": -0.0, "nested": [3.5, 100.0]}
    result = subprocess.run(
        [
            "node",
            "-e",
            "process.stdout.write(JSON.stringify(JSON.parse(process.argv[1])))",
            json.dumps(source),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert digest(source) == digest(json.loads(result.stdout))


def test_geometry_mismatch_fails_at_all_solver_entrypoints():
    import pytest

    from mapf.core.models import SimulationConfig
    from mapf.solvers.registry import get_solver

    instance = MAPFInstance(
        grid_width=3, grid_height=3, starts={"a": Point(0, 0)}, goals={"a": Point(2, 0)}
    )
    for name in ("CBS", "EECBS", "Prioritized", "HeatMap"):
        with pytest.raises(ValueError, match="geometry mismatch"):
            get_solver(name).solve(
                instance, SimulationConfig(grid_width=8, grid_height=8)
            )


SOLVERS = {
    "CBS": lambda: CentralizedCBSSolver(time_limit_sec=1),
    "focal-1": lambda: CentralizedEECBSSolver(suboptimality=1, time_limit_sec=1),
    "focal-1.1": lambda: CentralizedEECBSSolver(suboptimality=1.1, time_limit_sec=1),
    "Prioritized": CentralizedPrioritizedSolver,
}


@pytest.mark.parametrize("solver_id", SOLVERS)
@pytest.mark.parametrize("setting", list(SimulationSetting))
@pytest.mark.parametrize(
    "goals", list(permutations([(0, 0), (1, 0), (0, 1), (1, 1)], 2))
)
def test_central_solvers_against_independent_joint_state_oracle(
    solver_id, setting, goals
):
    """The original 192 cases, individually reported; the oracle shares no search code."""
    starts = ((0, 0), (1, 0))
    expected = optimal_joint_cost(starts, goals, 2, setting)
    instance = MAPFInstance(
        grid_width=2,
        grid_height=2,
        starts={"a": Point(*starts[0]), "b": Point(*starts[1])},
        goals={"a": Point(*goals[0]), "b": Point(*goals[1])},
    )
    result = SOLVERS[solver_id]().solve(
        instance, SimulationConfig(setting=setting, max_steps=20)
    )
    if expected is None:
        assert not result.success, result
        return
    if solver_id != "Prioritized":
        assert result.success, result
    if result.success:
        assert result.sum_of_costs >= expected
        if solver_id in ("CBS", "focal-1"):
            assert result.sum_of_costs == expected
        tracks = {
            a: [(p.x, p.y) for p in path.points] for a, path in result.paths.items()
        }
        assert_physical_paths(tracks, starts, goals, setting)
