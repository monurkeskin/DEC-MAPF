"""Qualified physical declarations around an independently checked native process."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from mapf.core.models import SimulationConfig
from mapf.solvers._native_io import NativeFiles, read_paths
from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol
from mapf.solvers.validation import validated_solver

_RESERVED_ARGUMENTS = frozenset({"--map", "-m", "--agents", "-a", "--output", "-o",
    "--outputPaths", "--agentNum", "-k", "--cutoffTime", "-t", "--suboptimality"})


def _validate_settings(family: str, settings: frozenset[str], arguments: Mapping[str, tuple[str, ...]]) -> None:
    if family not in ("eecbs", "cbsh2-rtc"):
        raise ValueError("Unknown external solver family")
    if not settings <= {"SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4"}:
        raise ValueError("Unknown declared physical setting")
    if family == "cbsh2-rtc" and not settings <= {"SETTING_1", "SETTING_2"}:
        raise ValueError("The article CBSH2-RTC profile supports SETTING_1 and SETTING_2 only")
    if len(settings) > 1 and not settings <= arguments.keys():
        raise ValueError("Multiple settings require explicit setting_arguments; use one setting for a specialized binary")


def _validate_arguments(arguments: Mapping[str, tuple[str, ...]]) -> None:
    supplied = {arg.split("=", 1)[0] for args in arguments.values() for arg in args}
    if supplied & _RESERVED_ARGUMENTS:
        raise ValueError("setting_arguments cannot override instance, output, cutoff or solver weight")


def _failure_reason(returncode: int, cost: int | None) -> str:
    if returncode != 0:
        return "native_execution_failure"
    reasons: dict[int | None, str] = {-1: "native_reported_limit", -2: "native_reported_no_solution"}
    return reasons.get(cost, "native_execution_failure")


def _output_tail(output: bytes | str | None) -> str:
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    return (output or "")[-4000:]


class ExternalBinarySolver(MAPFSolverProtocol):
    """Execute EECBS/CBSH2-RTC without treating reported costs as a validity proof.

    The constructor retains the adapter's public keyword and positional interface.
    File formats, invocation state and independent validation have separate owners.
    """

    def __init__(
        self,
        executable_path: str | Path,
        solver_name: str = "External-C++-Solver",
        suboptimality: float = 1.1,
        time_limit_sec: float = 60.0,
        supported_settings: frozenset[str] = frozenset(),
        coordinate_order: Literal["xy", "row-col"] = "xy",
        expected_sha256: str | None = None,
        solver_family: Literal["eecbs", "cbsh2-rtc"] | None = None,
        setting_arguments: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.executable_path = Path(executable_path)
        self._name = solver_name
        self.suboptimality = suboptimality
        self.time_limit_sec = time_limit_sec
        self.supported_settings = supported_settings
        self.coordinate_order = coordinate_order
        self.expected_sha256 = expected_sha256
        self.solver_family = solver_family or ("cbsh2-rtc" if "cbsh2" in solver_name.lower() else "eecbs")
        self.setting_arguments = dict(setting_arguments or {})
        _validate_settings(self.solver_family, supported_settings, self.setting_arguments)
        _validate_arguments(self.setting_arguments)
        if coordinate_order not in ("xy", "row-col"):
            raise ValueError("Unknown external coordinate order")

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_centralized(self) -> bool:
        return True

    @validated_solver
    def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution:
        if not self.executable_path.exists():
            return MAPFSolution(solver_name=self.name, is_centralized=True, success=False,
                                runtime_ms=0.0, metrics={"error": f"Executable not found at {self.executable_path}"})
        return _NativeRun(self, instance, config).execute()

    def _provenance(self, config: SimulationConfig) -> dict[str, Any]:
        if config.setting.name not in self.supported_settings:
            raise ValueError("External solver semantics must be explicitly declared for this setting")
        binary_hash = hashlib.sha256(self.executable_path.read_bytes()).hexdigest()
        if self.expected_sha256 and binary_hash != self.expected_sha256:
            raise ValueError("External binary identity changed")
        receipt = {"binary_sha256": binary_hash, "coordinate_order": self.coordinate_order,
                   "declared_settings": sorted(self.supported_settings),
                   "solver_family": self.solver_family, "setting": config.setting.name,
                   "setting_arguments": list(self.setting_arguments.get(config.setting.name, ())),
                   "qualification": "unqualified external adapter; not a certified optimal oracle"}
        return {**receipt, "solver_diagnostics": dict(receipt)}


class _NativeRun:
    """Own the bounded lifetime and diagnostic receipt of one native invocation."""

    def __init__(self, solver: ExternalBinarySolver, instance: MAPFInstance, config: SimulationConfig) -> None:
        self.started = time.perf_counter()
        self.solver, self.instance, self.config = solver, instance, config
        self.metrics = solver._provenance(config)
        self.timeout = (config.centralized_timeout_sec if "centralized_timeout_sec" in config.model_fields_set
                        else solver.time_limit_sec)
        self.metrics["cutoff_seconds"] = self.timeout
        self.metrics["solver_diagnostics"]["cutoff_seconds"] = self.timeout
        self.runtime_ms = 0.0

    def execute(self) -> MAPFSolution:
        with tempfile.TemporaryDirectory() as folder:
            files = NativeFiles(Path(folder))
            files.write_instance(self.instance)
            try:
                proc = subprocess.run(self._command(files), capture_output=True, check=False,
                                      timeout=self.timeout, text=True)
                self.runtime_ms = (time.perf_counter() - self.started) * 1000.0
                return self._result(files, proc)
            except subprocess.TimeoutExpired as exc:
                self.runtime_ms = (time.perf_counter() - self.started) * 1000.0
                self.metrics["solver_diagnostics"].update(
                    timed_out=True, stdout=_output_tail(exc.stdout), stderr=_output_tail(exc.stderr))
                return self._failure("Subprocess execution timed out.", termination_reason="timeout")

    def _command(self, files: NativeFiles) -> list[str]:
        cmd = [str(self.solver.executable_path), *files.arguments(len(self.instance.starts)),
               "--cutoffTime", str(self.timeout)]
        if self.solver.solver_family == "eecbs":
            cmd.extend(["--suboptimality", str(self.solver.suboptimality)])
        cmd.extend(self.solver.setting_arguments.get(self.config.setting.name, ()))
        return cmd

    def _failure(self, error: str, **details: Any) -> MAPFSolution:
        return MAPFSolution(solver_name=self.solver.name, is_centralized=True, success=False,
                            runtime_ms=self.runtime_ms, metrics={**self.metrics, "error": error, **details})

    def _result(self, files: NativeFiles, proc: subprocess.CompletedProcess[str]) -> MAPFSolution:
        statistics = files.read_statistics()
        reported_cost = int(statistics["solution cost"]) if "solution cost" in statistics else None
        self.metrics["solver_diagnostics"].update(statistics=statistics, exit_code=proc.returncode,
                                                stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:])
        if proc.returncode != 0 or not files.paths.exists():
            return self._failure("Binary failed or did not produce paths.txt", exit_code=proc.returncode,
                                 stdout=proc.stdout, termination_reason=_failure_reason(proc.returncode, reported_cost))
        paths = read_paths(files.paths, self.instance, self.solver.coordinate_order)
        sum_costs = sum(path.length for path in paths.values())
        self.metrics["solver_diagnostics"]["reported_cost_matches_paths"] = (
            reported_cost == sum_costs if reported_cost is not None else None)
        return MAPFSolution(
            solver_name=self.solver.name, is_centralized=True,
            success=len(paths) == len(self.instance.starts), paths=paths,
            makespan=max((path.length for path in paths.values()), default=0),
            sum_of_costs=reported_cost if reported_cost is not None else sum_costs,
            runtime_ms=self.runtime_ms, metrics={**self.metrics, "stdout": proc.stdout})


BaseBinarySolver = ExternalBinarySolver
