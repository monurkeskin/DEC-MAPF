from __future__ import annotations

import json
from pathlib import Path

from mapf.core.hashing import compute_instance_hash, compute_run_id
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.core.solution_validator import validate_solution
from mapf.metrics.cohort import evaluate_common_solved_cohort
from mapf.solvers import CentralizedEECBSSolver, DecentralizedNegotiationSolver
from mapf.solvers.base import MAPFInstance


def test_instance_hashing_determinism():
    """Verify compute_instance_hash is deterministic and sensitive to changes."""
    inst1 = MAPFInstance(
        grid_width=5,
        grid_height=5,
        starts={"A": Point(x=0, y=0), "B": Point(x=4, y=4)},
        goals={"A": Point(x=4, y=4), "B": Point(x=0, y=0)},
        obstacles={Point(x=2, y=2)},
    )
    inst2 = MAPFInstance(
        grid_width=5,
        grid_height=5,
        starts={"A": Point(x=0, y=0), "B": Point(x=4, y=4)},
        goals={"A": Point(x=4, y=4), "B": Point(x=0, y=0)},
        obstacles={Point(x=2, y=2)},
    )
    # Different setting
    h1 = compute_instance_hash(inst1, SimulationSetting.SETTING_4)
    h2 = compute_instance_hash(inst2, SimulationSetting.SETTING_4)
    assert h1 == h2
    assert h1.startswith("inst-")

    h3 = compute_instance_hash(inst1, SimulationSetting.SETTING_1)
    assert h1 != h3  # Setting must produce distinct hash

    # Modified goal
    inst3 = MAPFInstance(
        grid_width=5,
        grid_height=5,
        starts={"A": Point(x=0, y=0), "B": Point(x=4, y=4)},
        goals={"A": Point(x=3, y=4), "B": Point(x=0, y=0)},
        obstacles={Point(x=2, y=2)},
    )
    assert compute_instance_hash(inst3, SimulationSetting.SETTING_4) != h1


def test_run_id_determinism():
    """Verify compute_run_id generates repeatable content-addressed run identifiers."""
    h = "inst-abcdef0123456789"
    r1 = compute_run_id(h, "HeatMap", {"fov": 5, "setting": "SETTING_4"}, "e75c0dd")
    r2 = compute_run_id(h, "HeatMap", {"fov": 5, "setting": "SETTING_4"}, "e75c0dd")
    assert r1 == r2
    assert r1.startswith("run-")

    r3 = compute_run_id(h, "PathAware", {"fov": 5, "setting": "SETTING_4"}, "e75c0dd")
    assert r1 != r3


def test_frozen_suite_integrity():
    """Verify benchmarks/suites/regression_core.json exists, contains 32 valid instances with verified hashes."""
    suite_path = Path("benchmarks/suites/regression_core.json")
    assert suite_path.exists(), "regression_core.json must exist"

    with open(suite_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["suite_name"] == "regression_core"
    assert data["total_instances"] == 32
    assert len(data["instances"]) == 32

    for item in data["instances"]:
        starts = {aid: Point(x=p[0], y=p[1]) for aid, p in item["starts"].items()}
        goals = {aid: Point(x=p[0], y=p[1]) for aid, p in item["goals"].items()}
        obs = {Point(x=p[0], y=p[1]) for p in item.get("obstacles", [])}
        setting = getattr(SimulationSetting, item["setting"])

        inst = MAPFInstance(
            grid_width=item["grid_width"],
            grid_height=item["grid_height"],
            starts=starts,
            goals=goals,
            obstacles=obs,
        )

        expected_hash = compute_instance_hash(inst, setting)
        assert item["instance_hash"] == expected_hash, f"Hash mismatch for {item['instance_id']}"

        # Boundary checks
        for p in list(starts.values()) + list(goals.values()) + list(obs):
            assert 0 <= p.x < inst.grid_width
            assert 0 <= p.y < inst.grid_height


def test_run_core_subsample_and_validate():
    """Execute a subset of regression_core.json with solvers and assert 100% solution validity."""
    suite_path = Path("benchmarks/suites/regression_core.json")
    with open(suite_path, "r", encoding="utf-8") as f:
        instances = json.load(f)["instances"]

    # Pick 2 key counterexamples
    targets = [inst for inst in instances if inst["instance_id"] in ("2x2_swap_s4", "5x2_corridor_crossing_s4")]
    assert len(targets) == 2

    solvers = [
        DecentralizedNegotiationSolver("HeatMap"),
        CentralizedEECBSSolver(),
    ]

    for raw in targets:
        starts = {aid: Point(x=p[0], y=p[1]) for aid, p in raw["starts"].items()}
        goals = {aid: Point(x=p[0], y=p[1]) for aid, p in raw["goals"].items()}
        obs = {Point(x=p[0], y=p[1]) for p in raw.get("obstacles", [])}
        setting = getattr(SimulationSetting, raw["setting"])

        inst = MAPFInstance(
            grid_width=raw["grid_width"],
            grid_height=raw["grid_height"],
            starts=starts,
            goals=goals,
            obstacles=obs,
        )
        cfg = SimulationConfig(
            grid_width=inst.grid_width,
            grid_height=inst.grid_height,
            obstacles=obs,
            setting=setting,
            max_steps=15,
            centralized_timeout_sec=2,
            random_seed=42,
        )

        for solver in solvers:
            sol = solver.solve(inst, cfg)
            val = validate_solution(inst, sol.paths, setting)
            if sol.success:
                assert val.is_valid, f"{solver.name} returned invalid solution on {raw['instance_id']}: {val.errors}"


def test_common_solved_cohort_metrics():
    """Verify evaluate_common_solved_cohort handles common set pairing and ignores failed run costs."""
    sample_records = [
        {"instance_hash": "h1", "solver_name": "EECBS", "success": True, "makespan": 10, "sum_of_costs": 20, "runtime_ms": 5.0},
        {"instance_hash": "h1", "solver_name": "HeatMap", "success": True, "makespan": 12, "sum_of_costs": 22, "runtime_ms": 1.0},
        {"instance_hash": "h2", "solver_name": "EECBS", "success": True, "makespan": 15, "sum_of_costs": 30, "runtime_ms": 8.0},
        {"instance_hash": "h2", "solver_name": "HeatMap", "success": False, "makespan": 0, "sum_of_costs": 0, "runtime_ms": 2.0},
        {"instance_hash": "h3", "solver_name": "EECBS", "success": False, "makespan": 0, "sum_of_costs": 0, "runtime_ms": 100.0},
        {"instance_hash": "h3", "solver_name": "HeatMap", "success": True, "makespan": 8, "sum_of_costs": 16, "runtime_ms": 1.5},
    ]

    res = evaluate_common_solved_cohort(sample_records, "EECBS", "HeatMap")

    assert res.total_evaluated_instances == 3
    assert res.baseline_solved_count == 2
    assert res.test_solved_count == 2
    assert res.common_solved_count == 1  # Only h1 solved by both!
    assert res.baseline_only_count == 1   # h2
    assert res.test_only_count == 1       # h3
    assert res.neither_solved_count == 0

    # For h1: delta_ms = 12 - 10 = 2, delta_soc = 22 - 20 = 2, opt_gap = 2 / 20 = 0.10
    assert res.mean_delta_makespan == 2.0
    assert res.mean_delta_soc == 2.0
    assert res.mean_optimality_gap == 0.10
