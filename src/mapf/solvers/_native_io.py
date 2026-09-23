"""MovingAI input and native text output; no process or solver policy decisions."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

from mapf.core.models import Path as AgentPath
from mapf.core.models import Point
from mapf.core.movingai import format_movingai_map
from mapf.solvers.base import MAPFInstance


@dataclass(frozen=True)
class NativeFiles:
    root: Path

    @property
    def statistics(self) -> Path:
        return self.root / "output.csv"

    @property
    def paths(self) -> Path:
        return self.root / "paths.txt"

    def write_instance(self, instance: MAPFInstance) -> None:
        (self.root / "grid.map").write_text(format_movingai_map(
            instance.grid_width, instance.grid_height, instance.obstacles))
        lines = ["version 1"]
        for index, (agent, start) in enumerate(instance.starts.items()):
            goal = instance.goals[agent]
            lines.append(
                f"{index}\tgrid.map\t{instance.grid_width}\t{instance.grid_height}\t"
                f"{start.x}\t{start.y}\t{goal.x}\t{goal.y}\t{start.manhattan_distance(goal)}")
        (self.root / "scenario.scen").write_text("\n".join(lines) + "\n")

    def arguments(self, agent_count: int) -> list[str]:
        return ["--map", str(self.root / "grid.map"),
                "--agents", str(self.root / "scenario.scen"),
                "--output", str(self.statistics), "--outputPaths", str(self.paths),
                "--agentNum", str(agent_count)]

    def read_statistics(self) -> dict[str, str]:
        if not self.statistics.exists():
            return {}
        with self.statistics.open("rb") as handle:
            raw = handle.read(65537)
        if len(raw) > 65536:
            return {"_diagnostic": "statistics exceed the 64 KiB snapshot limit"}
        # A killed writer can leave its final CSV record incomplete. Preserve the
        # last complete row, never interpret a partial cost or counter as measured.
        text = raw[:raw.rfind(b"\n") + 1].decode("utf-8", errors="replace")
        result = {}
        try:
            for record in csv.DictReader(io.StringIO(text), strict=True):
                if None not in record and None not in record.values():
                    result = {key.strip(): value for key, value in record.items()}
        except csv.Error:
            result["_diagnostic"] = "incomplete or malformed native statistics"
        return result


def _point(text: str, instance: MAPFInstance, order: str) -> Point:
    pair = re.fullmatch(r"\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*", text)
    if pair:
        x, y = map(int, pair.groups())
        return Point(x, y) if order == "xy" else Point(y, x)
    if not re.fullmatch(r"\s*\d+\s*", text):
        raise ValueError("Malformed external coordinate or linear location")
    index = int(text)
    if index >= instance.grid_width * instance.grid_height:
        raise ValueError("External linear location is outside the map")
    return Point(index % instance.grid_width, index // instance.grid_width)


def read_paths(path: Path, instance: MAPFInstance, coordinate_order: str) -> dict[str, AgentPath]:
    agents = list(instance.starts)
    result: dict[str, AgentPath] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = re.fullmatch(r"Agent\s+(\d+)\s*:(.*)", line)
        if record is None:
            raise ValueError("Malformed external path record")
        index, raw_path = record.groups()
        if int(index) >= len(agents) or agents[int(index)] in result:
            raise ValueError("Unknown or duplicate external agent index")
        steps = raw_path.strip().split("->")
        if not steps[-1].strip():
            steps.pop()  # Published formats allow one trailing arrow.
        if steps:
            result[agents[int(index)]] = AgentPath(points=[_point(step, instance, coordinate_order) for step in steps])
    return result
