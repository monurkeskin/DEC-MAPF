"""Independent, hand-calculated regression witnesses for the workspace takeover."""

import pytest

from mapf.application.scenarios import ScenarioService
from mapf.core.models import Path, Point, SimulationSetting
from mapf.core.solution_validator import validate_solution
from mapf.gui.frame_builder import build_solver_run_result
from mapf.solvers.base import MAPFInstance, MAPFSolution


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


@pytest.mark.parametrize("solver_id", ["CBS", "focal-1", "focal-1.1", "Prioritized"])
def test_central_solvers_against_independent_joint_state_oracle(solver_id):
    """48 cases per solver, all four settings; Dijkstra counts per-agent actions."""
    import heapq
    import itertools

    from mapf.core.models import SimulationConfig
    from mapf.solvers.cbs import CentralizedCBSSolver
    from mapf.solvers.eecbs import CentralizedEECBSSolver
    from mapf.solvers.prioritized import CentralizedPrioritizedSolver

    def oracle(starts, goals, size, setting):
        counter = itertools.count()
        heap = [(0, next(counter), starts)]
        best = {starts: 0}
        while heap:
            cost, _, state = heapq.heappop(heap)
            if cost != best[state]:
                continue
            if all(p is None or p == g for p, g in zip(state, goals, strict=True)):
                return cost
            choices = []
            for p, g in zip(state, goals, strict=True):
                if p is None:
                    choices.append([None])
                    continue
                if p == g:
                    choices.append([None] if setting.disappear_at_target else [g])
                    continue
                x, y = p
                candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
                if setting.allow_wait:
                    candidates.append(p)
                choices.append(
                    [(a, b) for a, b in candidates if 0 <= a < size and 0 <= b < size]
                )
            for nxt in itertools.product(*choices):
                if nxt[0] is not None and nxt[0] == nxt[1]:
                    continue
                if (
                    None not in nxt
                    and nxt[0] == state[1]
                    and nxt[1] == state[0]
                    and nxt[0] != nxt[1]
                ):
                    continue
                value = cost + sum(
                    p is not None and p != g for p, g in zip(state, goals, strict=True)
                )
                if value < best.get(nxt, 10**6):
                    best[nxt] = value
                    heapq.heappush(heap, (value, next(counter), nxt))
        return None

    for setting in SimulationSetting:
        cells = [(0, 0), (1, 0), (0, 1), (1, 1)]
        starts = ((0, 0), (1, 0))
        for goals in itertools.permutations(cells, 2):
            expected = oracle(starts, goals, 2, setting)
            instance = MAPFInstance(
                grid_width=2,
                grid_height=2,
                starts={"a": Point(*starts[0]), "b": Point(*starts[1])},
                goals={"a": Point(*goals[0]), "b": Point(*goals[1])},
            )
            solver = {"CBS": lambda: CentralizedCBSSolver(time_limit_sec=1),
                      "focal-1": lambda: CentralizedEECBSSolver(suboptimality=1, time_limit_sec=1),
                      "focal-1.1": lambda: CentralizedEECBSSolver(suboptimality=1.1, time_limit_sec=1),
                      "Prioritized": CentralizedPrioritizedSolver}[solver_id]()
            result = solver.solve(
                instance, SimulationConfig(setting=setting, max_steps=20)
            )
            assert (not result.success if expected is None else result.success or solver_id == "Prioritized"), (
                setting,
                goals,
                expected,
                result,
            )
            if result.success:
                assert result.sum_of_costs >= expected
                assert (result.sum_of_costs == expected if solver_id in ("CBS", "focal-1") else True), (
                    setting,
                    goals,
                    expected,
                    result.sum_of_costs,
                )
                # Physical witnesses do not rely on the production validator.
                tracks = {a: [(p.x, p.y) for p in path.points] for a, path in result.paths.items()}
                for i, aid in enumerate(("a", "b")):
                    assert tracks[aid][0] == starts[i] and tracks[aid][-1] == goals[i]
                    for old, new in zip(tracks[aid], tracks[aid][1:]):
                        distance = abs(old[0]-new[0]) + abs(old[1]-new[1])
                        assert distance == 1 or distance == 0 and (setting.allow_wait or old == goals[i])
                        if old == goals[i]:
                            assert new == old
                for t in range(max(map(len, tracks.values()))):
                    p = [tracks[a][t] if t < len(tracks[a]) else None if setting.disappear_at_target
                         else tracks[a][-1] for a in ("a", "b")]
                    assert p[0] is None or p[0] != p[1]
                    if t and None not in p:
                        assert not (p[0] == tracks["b"][min(t-1, len(tracks["b"])-1)] and
                                    p[1] == tracks["a"][min(t-1, len(tracks["a"])-1)])
