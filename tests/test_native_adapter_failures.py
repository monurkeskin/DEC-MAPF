"""Native boundary fixtures validate invocation and receipts, not C++ optimality."""

import subprocess
from pathlib import Path

import pytest

from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.solvers import binary_runner
from mapf.solvers.base import MAPFInstance
from mapf.solvers.binary_runner import ExternalBinarySolver


@pytest.fixture
def invocation(tmp_path, monkeypatch):
    binary = tmp_path / "fixture"
    binary.write_bytes(b"synthetic executable identity")
    output = {"paths": "Agent 0: 0->1->2", "csv": None, "returncode": 0}

    def run(argv, **kwargs):
        assert kwargs == {"capture_output": True, "check": False, "timeout": 2.5, "text": True}
        assert argv[argv.index("--cutoffTime") + 1] == "2.5"
        for key, flag in (("paths", "--outputPaths"), ("csv", "--output")):
            if output[key] is not None:
                Path(argv[argv.index(flag) + 1]).write_text(output[key])
        return subprocess.CompletedProcess(argv, output["returncode"], "stdout", "stderr")

    monkeypatch.setattr(binary_runner.subprocess, "run", run)
    solver = ExternalBinarySolver(binary, supported_settings=frozenset({"SETTING_2"}), time_limit_sec=2.5)
    instance = MAPFInstance(grid_width=3, grid_height=2, starts={"a": Point(0, 0)}, goals={"a": Point(2, 0)})
    config = SimulationConfig(setting=SimulationSetting.SETTING_2)
    return solver, instance, config, output


@pytest.mark.parametrize("order", ["yx", "", None])
def test_unknown_coordinate_order_is_rejected_before_execution(tmp_path, order):
    with pytest.raises(ValueError, match="coordinate order"):
        ExternalBinarySolver(tmp_path / "fixture", coordinate_order=order)


def test_timeout_retains_bounded_process_diagnostics(invocation, monkeypatch):
    solver, instance, config, _ = invocation

    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"x" * 4500, stderr=b"stalled\xff")

    monkeypatch.setattr(binary_runner.subprocess, "run", timeout)
    result = solver.solve(instance, config)
    assert not result.success and result.metrics["termination_reason"] == "timeout"
    diagnostic = result.metrics["solver_diagnostics"]
    assert diagnostic["stdout"] == "x" * 4000
    assert diagnostic["stderr"] == "stalled\ufffd"
    assert diagnostic["timed_out"] is True and diagnostic["cutoff_seconds"] == 2.5


@pytest.mark.parametrize(("path", "message"), [
    ("a: 0->1->2", "Malformed external path"),
    ("Agent 1: 0->1->2", "Unknown or duplicate"),
    ("Agent 0: 0->1->2\nAgent 0: 0->1->2", "Unknown or duplicate"),
    ("Agent 0: 0->6", "outside the map"),
    ("Agent 0: 0->(1,)", "Malformed external coordinate"),
    ("Agent 0: 0->-1", "Malformed external coordinate"),
    ("Agent 0: 0->1->->", "Malformed external coordinate"),
])
def test_malformed_native_path_cannot_be_a_solution(invocation, path, message):
    solver, instance, config, output = invocation
    output["paths"] = path
    with pytest.raises(ValueError, match=message):
        solver.solve(instance, config)


@pytest.mark.parametrize(("returncode", "cost", "reason"), [
    (0, -1, "native_reported_limit"), (0, -2, "native_reported_no_solution"),
    (3, -1, "native_execution_failure"), (0, None, "native_execution_failure"),
])
def test_native_unsolved_outcomes_are_not_interchangeable(invocation, returncode, cost, reason):
    solver, instance, config, output = invocation
    output.update(paths=None, returncode=returncode, csv=None if cost is None else f"solution cost\n{cost}\n")
    result = solver.solve(instance, config)
    assert not result.success and result.metrics["termination_reason"] == reason
    assert result.metrics["solver_diagnostics"]["exit_code"] == returncode


@pytest.mark.parametrize("csv", [None, "", "solution cost\n"])
def test_no_statistics_does_not_erase_valid_paths(invocation, csv):
    solver, instance, config, output = invocation
    output.update(csv=csv, paths="\nAgent 0: 0->1->2->\n")
    result = solver.solve(instance, config)
    assert result.success and result.sum_of_costs == 2
    assert result.metrics["solver_diagnostics"]["reported_cost_matches_paths"] is None


def test_last_statistics_record_preserves_reported_and_recomputed_costs(invocation):
    solver, instance, config, output = invocation
    output["csv"] = " solution cost ,runtime\n999,0.2\n2,0.3\n"
    result = solver.solve(instance, config)
    assert result.success and result.metrics["solver_reported_sum_of_costs"] == 2
    assert result.metrics["solver_diagnostics"]["statistics"]["runtime"] == "0.3"


def test_modified_native_identity_is_rejected_by_direct_adapter(invocation):
    solver, instance, config, _ = invocation
    solver.expected_sha256 = "0" * 64
    with pytest.raises(ValueError, match="identity changed"):
        solver.solve(instance, config)


@pytest.mark.parametrize("kwargs", [{"solver_family": "unknown"}, {"supported_settings": frozenset({"unknown"})}])
def test_invalid_native_declarations_are_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError, match="Unknown"):
        ExternalBinarySolver(tmp_path / "fixture", **kwargs)
