import pytest

from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.negotiation.conflict import detect_conflicts
from mapf.solvers.base import MAPFInstance
from mapf.solvers.cbs import CentralizedCBSSolver
from mapf.solvers.decentralized import DecentralizedNegotiationSolver
from mapf.solvers.prioritized import CentralizedPrioritizedSolver


@pytest.fixture
def crossing_instance() -> MAPFInstance:
    # 2 agents crossing at (2, 2)
    return MAPFInstance(
        starts={"A1": Point(x=0, y=2), "A2": Point(x=2, y=0)},
        goals={"A1": Point(x=4, y=2), "A2": Point(x=2, y=4)},
        grid_width=6,
        grid_height=6,
    )


def test_centralized_cbs_solver(crossing_instance: MAPFInstance):
    config = SimulationConfig(grid_width=6, grid_height=6, setting=SimulationSetting.SETTING_4)
    solver = CentralizedCBSSolver(time_limit_sec=5.0)

    solution = solver.solve(crossing_instance, config)
    assert solution.success is True
    assert solution.is_centralized is True
    assert len(solution.paths) == 2

    # Verify zero conflicts
    conflicts = detect_conflicts(solution.paths)
    assert len(conflicts) == 0


def test_centralized_prioritized_solver(crossing_instance: MAPFInstance):
    config = SimulationConfig(grid_width=6, grid_height=6, setting=SimulationSetting.SETTING_4)
    solver = CentralizedPrioritizedSolver()

    solution = solver.solve(crossing_instance, config)
    assert solution.success is True
    assert solution.is_centralized is True

    conflicts = detect_conflicts(solution.paths)
    assert len(conflicts) == 0


def test_decentralized_negotiation_solver_unified_interface(crossing_instance: MAPFInstance):
    config = SimulationConfig(grid_width=6, grid_height=6, setting=SimulationSetting.SETTING_4)
    solver = DecentralizedNegotiationSolver(strategy="PathAware")

    solution = solver.solve(crossing_instance, config)
    assert solution.success is True
    assert solution.is_centralized is False
    assert "negotiation_count" in solution.metrics


def test_eecbs_solver(crossing_instance: MAPFInstance):
    from mapf.solvers.eecbs import CentralizedEECBSSolver

    config = SimulationConfig(grid_width=6, grid_height=6, setting=SimulationSetting.SETTING_4)
    solver = CentralizedEECBSSolver(suboptimality=1.1, time_limit_sec=5.0)

    solution = solver.solve(crossing_instance, config)
    assert solution.success is True
    assert solution.is_centralized is True
    assert len(solution.paths) == 2
    conflicts = detect_conflicts(solution.paths)
    assert len(conflicts) == 0


def test_movingai_map_and_stern_generator():
    from mapf.core.movingai import (
        format_movingai_map,
        generate_benchmark_map,
        generate_stern_scenario,
        parse_movingai_map,
    )

    obstacles = generate_benchmark_map(width=16, height=16, obstacle_density=0.10, seed=42)
    assert len(obstacles) == int(16 * 16 * 0.10)

    formatted = format_movingai_map(16, 16, obstacles)
    w, h, parsed_obs = parse_movingai_map(formatted)
    assert w == 16
    assert h == 16
    assert parsed_obs == obstacles

    pairs = generate_stern_scenario(16, 16, obstacles, num_agents=20, min_dist=4, max_dist=24, seed=42)
    assert len(pairs) == 20
    for s, g in pairs:
        assert s not in obstacles
        assert g not in obstacles
        assert 4 <= s.manhattan_distance(g) <= 24


def test_commitment_types_in_negotiation(crossing_instance: MAPFInstance):
    from mapf.core.models import CommitmentType

    for c_type in [CommitmentType.STANDARD, CommitmentType.DYNAMIC, CommitmentType.ZERO]:
        config = SimulationConfig(
            grid_width=6,
            grid_height=6,
            setting=SimulationSetting.SETTING_4,
            commitment_type=c_type,
        )
        solver = DecentralizedNegotiationSolver(strategy="HeatMap")
        solution = solver.solve(crossing_instance, config)
        assert solution.success is True


def test_external_binary_solver_parser_fixture(tmp_path, crossing_instance: MAPFInstance):
    """Verify K09: External oracle adapter passes golden parser fixture and path validation without requiring C++ binary."""
    from mapf.core.solution_validator import validate_solution
    from mapf.solvers.binary_runner import ExternalBinarySolver

    # 1. Non-existent binary returns graceful failure
    solver = ExternalBinarySolver(executable_path=tmp_path / "non_existent_solver")
    cfg = SimulationConfig(grid_width=6, grid_height=6, setting=SimulationSetting.SETTING_4)
    sol = solver.solve(crossing_instance, cfg)
    assert sol.success is False
    assert "not found" in sol.metrics.get("error", "").lower()

    # 2. Mock script producing golden paths.txt output
    mock_bin = tmp_path / "mock_solver.sh"
    mock_bin.write_text("""#!/bin/sh
for arg in "$@"; do
    if [ "$prev" = "--outputPaths" ]; then
        out_paths="$arg"
    fi
    prev="$arg"
done
cat << 'EOF' > "$out_paths"
Agent 0: (0,2)->(1,2)->(2,2)->(3,2)->(4,2)
Agent 1: (2,0)->(2,1)->(1,1)->(1,2)->(1,3)->(2,3)->(2,4)
EOF
exit 0
""")
    mock_bin.chmod(0o755)

    solver_mock = ExternalBinarySolver(executable_path=mock_bin, solver_name="ParserFixture",
                                       supported_settings=frozenset({"SETTING_4"}))
    sol_mock = solver_mock.solve(crossing_instance, cfg)

    assert sol_mock.success is True
    assert len(sol_mock.paths) == 2
    assert "A1" in sol_mock.paths
    assert "A2" in sol_mock.paths

    # Validate physical correctness of golden paths
    val = validate_solution(crossing_instance, sol_mock.paths, cfg.setting)
    assert val.is_valid is True, f"Parsed golden paths must be valid: {val.errors}"
