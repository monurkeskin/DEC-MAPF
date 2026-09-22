from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from mapf.core.models import Path as AgentPath
from mapf.core.models import Point, SimulationConfig
from mapf.core.movingai import format_movingai_map
from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol
from mapf.solvers.validation import validated_solver


class ExternalBinarySolver(MAPFSolverProtocol):
    """Adapter executing compiled external C++ binaries (e.g. EECBS, CBSH2-RTC).

    Automates the workflow originally written in Furkan Cantürk's run_cbs.py:
    1. Formats instance into MovingAI .map and .scen files.
    2. Invokes external executable with cutoff time and suboptimality parameters.
    3. Parses resulting paths and statistics into MAPFSolution.
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
        if self.solver_family not in ("eecbs", "cbsh2-rtc"):
            raise ValueError("Unknown external solver family")
        self.setting_arguments = dict(setting_arguments or {})
        if not supported_settings <= {"SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4"}:
            raise ValueError("Unknown declared physical setting")
        if self.solver_family == "cbsh2-rtc" and not supported_settings <= {"SETTING_1", "SETTING_2"}:
            raise ValueError("The article CBSH2-RTC profile supports SETTING_1 and SETTING_2 only")
        if len(supported_settings) > 1 and not supported_settings <= self.setting_arguments.keys():
            raise ValueError("Multiple settings require explicit setting_arguments; use one setting for a specialized binary")
        reserved = {"--map", "-m", "--agents", "-a", "--output", "-o", "--outputPaths",
                    "--agentNum", "-k", "--cutoffTime", "-t", "--suboptimality"}
        if any(arg.split("=", 1)[0] in reserved for args in self.setting_arguments.values() for arg in args):
            raise ValueError("setting_arguments cannot override instance, output, cutoff or solver weight")

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_centralized(self) -> bool:
        return True

    @validated_solver
    def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution:
        start_time = time.perf_counter()

        if not self.executable_path.exists():
            return MAPFSolution(
                solver_name=self.name,
                is_centralized=True,
                success=False,
                runtime_ms=0.0,
                metrics={"error": f"Executable not found at {self.executable_path}"},
            )

        if config.setting.name not in self.supported_settings:
            raise ValueError("External solver semantics must be explicitly declared for this setting")
        binary_hash = hashlib.sha256(self.executable_path.read_bytes()).hexdigest()
        if self.expected_sha256 and binary_hash != self.expected_sha256:
            raise ValueError("External binary identity changed")
        provenance: dict[str, Any] = {"binary_sha256": binary_hash, "coordinate_order": self.coordinate_order,
                      "declared_settings": sorted(self.supported_settings),
                      "solver_family": self.solver_family, "setting": config.setting.name,
                      "setting_arguments": list(self.setting_arguments.get(config.setting.name, ())),
                      "qualification": "unqualified external adapter; not a certified optimal oracle"}
        # A compact, durable execution receipt survives the headless replay/export
        # boundary. Historical stdout alone is neither a validity nor cost proof.
        provenance["solver_diagnostics"] = dict(provenance)
        timeout = config.centralized_timeout_sec if "centralized_timeout_sec" in config.model_fields_set else self.time_limit_sec
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            map_file = tmppath / "grid.map"
            scen_file = tmppath / "scenario.scen"
            out_csv = tmppath / "output.csv"
            out_paths = tmppath / "paths.txt"

            # 1. Write MovingAI .map
            map_content = format_movingai_map(instance.grid_width, instance.grid_height, instance.obstacles)
            map_file.write_text(map_content)

            # 2. Write MovingAI .scen
            scen_lines = ["version 1"]
            for idx, (a_id, s_pt) in enumerate(instance.starts.items()):
                g_pt = instance.goals[a_id]
                dist = s_pt.manhattan_distance(g_pt)
                scen_lines.append(
                    f"{idx}\tgrid.map\t{instance.grid_width}\t{instance.grid_height}\t{s_pt.x}\t{s_pt.y}\t{g_pt.x}\t{g_pt.y}\t{dist}"
                )
            scen_file.write_text("\n".join(scen_lines) + "\n")

            # 3. Formulate CLI arguments
            k = len(instance.starts)
            cmd = [
                str(self.executable_path),
                "--map", str(map_file),
                "--agents", str(scen_file),
                "--output", str(out_csv),
                "--outputPaths", str(out_paths),
                "--agentNum", str(k),
                "--cutoffTime", str(timeout),
            ]
            if self.solver_family == "eecbs":
                cmd.extend(["--suboptimality", str(self.suboptimality)])
            cmd.extend(self.setting_arguments.get(config.setting.name, ()))
            provenance["cutoff_seconds"] = timeout
            provenance["solver_diagnostics"]["cutoff_seconds"] = timeout

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    check=False,
                    timeout=timeout,
                    text=True,
                )
                runtime_ms = (time.perf_counter() - start_time) * 1000.0
                statistics = {}
                if out_csv.exists():
                    with out_csv.open() as handle:
                        records = list(csv.DictReader(handle))
                    if records:
                        statistics = {key.strip(): value for key, value in records[-1].items()}
                reported_cost = int(statistics["solution cost"]) if "solution cost" in statistics else None
                provenance["solver_diagnostics"].update(
                    statistics=statistics, exit_code=proc.returncode,
                    stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:])

                if proc.returncode != 0 or not out_paths.exists():
                    reason = ("native_reported_limit" if proc.returncode == 0 and reported_cost == -1 else
                              "native_reported_no_solution" if proc.returncode == 0 and reported_cost == -2 else
                              "native_execution_failure")
                    return MAPFSolution(
                        solver_name=self.name,
                        is_centralized=True,
                        success=False,
                        runtime_ms=runtime_ms,
                        metrics={**provenance, "error": "Binary failed or did not produce paths.txt",
                                 "termination_reason": reason, "exit_code": proc.returncode, "stdout": proc.stdout},
                    )

                # 4. Parse paths.txt: format "Agent 0: (x,y)->(x,y)->..." or index format
                parsed_paths: dict[str, AgentPath] = {}
                agent_ids = list(instance.starts.keys())
                for line in out_paths.read_text().splitlines():
                    if not line.strip():
                        continue
                    if not re.fullmatch(r"Agent\s+\d+\s*:.*", line):
                        raise ValueError("Malformed external path record")
                    header, raw_path = line.split(":", 1)
                    idx_str = "".join(filter(str.isdigit, header))
                    if not idx_str:
                        continue
                    ag_idx = int(idx_str)
                    if ag_idx >= len(agent_ids) or agent_ids[ag_idx] in parsed_paths:
                        raise ValueError("Unknown or duplicate external agent index")
                    if ag_idx < len(agent_ids):
                        ag_name = agent_ids[ag_idx]
                        steps = raw_path.strip().split("->")
                        if steps[-1].strip() == "":
                            steps.pop()  # Both published formats may have one trailing arrow.
                        pts: list[Point] = []
                        for s in steps:
                            pair = re.fullmatch(r"\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*", s)
                            if pair:
                                x, y = map(int, pair.groups())
                                pts.append(Point(x, y) if self.coordinate_order == "xy" else Point(y, x))
                            elif re.fullmatch(r"\s*\d+\s*", s):
                                index = int(s)
                                if index >= instance.grid_width * instance.grid_height:
                                    raise ValueError("External linear location is outside the map")
                                pts.append(Point(index % instance.grid_width, index // instance.grid_width))
                            else:
                                raise ValueError("Malformed external coordinate or linear location")
                        if pts:
                            parsed_paths[ag_name] = AgentPath(points=pts)

                success = len(parsed_paths) == k
                makespan = max((p.length for p in parsed_paths.values()), default=0)
                sum_costs = sum(p.length for p in parsed_paths.values())
                provenance["solver_diagnostics"]["reported_cost_matches_paths"] = (
                    reported_cost == sum_costs if reported_cost is not None else None)

                return MAPFSolution(
                    solver_name=self.name,
                    is_centralized=True,
                    success=success,
                    paths=parsed_paths,
                    makespan=makespan,
                    sum_of_costs=reported_cost if reported_cost is not None else sum_costs,
                    runtime_ms=runtime_ms,
                    metrics={**provenance, "stdout": proc.stdout},
                )
            except subprocess.TimeoutExpired:
                return MAPFSolution(
                    solver_name=self.name,
                    is_centralized=True,
                    success=False,
                    runtime_ms=(time.perf_counter() - start_time) * 1000.0,
                    metrics={**provenance, "error": "Subprocess execution timed out.", "termination_reason": "timeout"},
                )


# Alias conforming to plug-and-play solver conventions
BaseBinarySolver = ExternalBinarySolver
