"""MovingAI text boundaries and coordinate-trajectory export compatibility.

Files contain coordinates, not movement semantics: DEC-MAPF uses four-connected
motion even when a scenario's stored reference distance came from octile search.
Synthetic generation lives in sampling; its original imports remain available.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from mapf.core.models import Point
from mapf.core.sampling import generate_benchmark_map, generate_stern_scenario

__all__ = [
    "ScenarioRow",
    "export_planviz_json",
    "export_standard_paths",
    "format_movingai_map",
    "format_movingai_scen",
    "generate_benchmark_map",
    "generate_stern_scenario",
    "parse_movingai_map",
    "parse_movingai_rows",
    "parse_movingai_scen",
]


def parse_movingai_map(content: str) -> tuple[int, int, set[Point]]:
    """Parse MovingAI .map format (Stern et al. 2019b).

    Returns:
        tuple of (width, height, set of obstacle Points)
    """
    lines = content.strip().splitlines()
    if not lines or lines[0].strip() != "type octile":
        raise ValueError(
            "MovingAI map must begin with type octile and a complete header"
        )
    width, height, map_start_idx = _map_header(lines)
    grid_lines = lines[map_start_idx:]
    _validate_map_body(grid_lines, width, height)
    obstacles = {
        Point(x=x, y=y)
        for y, row in enumerate(grid_lines)
        for x, char in enumerate(row)
        if char in "@TOW"
    }
    return width, height, obstacles


def _map_header(lines: list[str]) -> tuple[int, int, int]:
    dimensions: dict[str, int] = {}
    for index, line in enumerate(lines[1:], 1):
        fields = line.split()
        if fields == ["map"]:
            if dimensions.keys() != {"width", "height"}:
                raise ValueError("MovingAI map requires width and height before map")
            return dimensions["width"], dimensions["height"], index + 1
        name, value = _header_dimension(fields)
        if name in dimensions:
            raise ValueError(f"Duplicate MovingAI map dimension: {name}")
        dimensions[name] = value
    raise ValueError("MovingAI map requires a map body marker")


def _header_dimension(fields: list[str]) -> tuple[str, int]:
    if len(fields) != 2 or fields[0] not in {"width", "height"}:
        raise ValueError("MovingAI map dimensions require a name and integer value")
    try:
        return fields[0], int(fields[1])
    except ValueError:
        raise ValueError("MovingAI map dimensions require integer values") from None


def _validate_map_body(rows: list[str], width: int, height: int) -> None:
    dimensions_valid = min(width, height) > 0
    row_widths = {len(row) for row in rows}
    rectangular = (len(rows), row_widths) == (height, {width})
    if not dimensions_valid or not rectangular:
        raise ValueError("MovingAI map dimensions do not match its rectangular body")
    terrain = set("".join(rows))
    if not terrain.issubset(".GS@TOW"):
        raise ValueError("Unsupported MovingAI terrain symbol")


def format_movingai_map(width: int, height: int, obstacles: set[Point]) -> str:
    """Format grid and obstacles into standard MovingAI .map format."""
    lines = [
        "type octile",
        f"height {height}",
        f"width {width}",
        "map",
    ]
    for y in range(height):
        row_chars = []
        for x in range(width):
            if Point(x=x, y=y) in obstacles:
                row_chars.append("@")
            else:
                row_chars.append(".")
        lines.append("".join(row_chars))
    return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class ScenarioRow:
    """A validated agent row, retaining its declared map and reference distance.

    `reference_distance` is source metadata, never a four-connected certificate.
    `width` and `height` retain the declaration even when the caller explicitly
    supplies different coordinate bounds for a recorded archive repair.
    """

    map_name: str
    width: int
    height: int
    start: Point
    goal: Point
    reference_distance: float

    def __post_init__(self) -> None:
        if min(self.width, self.height) <= 0:
            raise ValueError("Positive declared dimensions required")
        _validate_scenario_distance(self.reference_distance)

    @property
    def dimensions(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def pair(self) -> tuple[Point, Point]:
        return self.start, self.goal


def parse_movingai_rows(
    content: str,
    *,
    coordinate_bounds: tuple[int, int] | None = None,
) -> list[ScenarioRow]:
    """Read ordered version 1/1.0 rows, validating the whole document.

    Blank lines and comments are accepted. An explicit `coordinate_bounds`
    validates coordinates against the supplied map for archive admission;
    callers must still reject or record disagreeing declared dimensions.
    No source text or row metadata is modified.
    """
    lines = content.strip().splitlines()
    if not lines or lines[0].split() not in (["version", "1"], ["version", "1.0"]):
        raise ValueError("MovingAI scenario header must be version 1 or 1.0")
    rows = []
    for line in lines[1:]:
        clean = line.strip()
        if clean and not clean.startswith("#"):
            rows.append(_scenario_row(clean.split(), coordinate_bounds))
    return rows


def parse_movingai_scen(content: str) -> list[tuple[Point, Point]]:
    """Return start/goal pairs after validating every MovingAI scenario row."""
    return [row.pair for row in parse_movingai_rows(content)]


def _scenario_row(parts: list[str], bounds: tuple[int, int] | None) -> ScenarioRow:
    if len(parts) != 9:
        raise ValueError("MovingAI scenario rows require nine columns")
    try:
        start_x, start_y, goal_x, goal_y = (int(value) for value in parts[4:8])
        width, height = int(parts[2]), int(parts[3])
        distance = float(parts[8])
        effective_width, effective_height = bounds or (width, height)
        start = _scenario_point(start_x, start_y, effective_width, effective_height)
        goal = _scenario_point(goal_x, goal_y, effective_width, effective_height)
        return ScenarioRow(parts[1], width, height, start, goal, distance)
    except ValueError:
        raise ValueError("Malformed MovingAI scenario row") from None


def _validate_scenario_distance(distance: float) -> None:
    if not math.isfinite(distance) or distance < 0:
        raise ValueError("Invalid scenario distance")


def _scenario_point(x: int, y: int, width: int, height: int) -> Point:
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError("Scenario coordinates violate the declared map")
    return Point(x=x, y=y)


def format_movingai_scen(
    pairs: list[tuple[Point, Point]],
    map_name: str,
    width: int,
    height: int,
) -> str:
    """Write MovingAI-shaped rows with Manhattan lower bounds as metadata.

    This convenience formatter has no obstacle map and cannot certify optimal
    lengths. Imports and article admission recompute four-connected distances;
    external tools requiring octile-optimal distances need a separate producer.
    """
    lines = ["version 1"]
    for idx, (s, g) in enumerate(pairs):
        bucket = idx % 10
        dist = s.manhattan_distance(g)
        lines.append(
            f"{bucket}\t{map_name}\t{width}\t{height}\t{s.x}\t{s.y}\t{g.x}\t{g.y}\t{dist:.8f}"
        )
    return "\n".join(lines) + "\n"


def export_standard_paths(solution_paths: dict[str, Any]) -> str:
    """Export agent trajectories to DEC-MAPF coordinate text.

    Format:
        Agent 0: (x0,y0)->(x1,y1)->(x2,y2)...
    """
    lines = []
    for agent_id, path in sorted(solution_paths.items()):
        points_str = "->".join(f"({p.x},{p.y})" for p in path.points)
        lines.append(f"{agent_id}: {points_str}")
    return "\n".join(lines) + "\n"


def export_planviz_json(
    solution_paths: dict[str, Any],
    map_name: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Return the compatibility coordinate-trajectory payload (MAPF_POST).

    This is a DEC-MAPF dialect, not a certified upstream PlanViz action stream.
    Prefer run bundles for round-trip import and the GUI for supported replay.
    """
    agent_names = sorted(solution_paths.keys())
    team_size = len(agent_names)

    starts: list[list[int]] = []
    actual_paths: list[str] = []

    for name in agent_names:
        p = solution_paths[name]
        if p.points:
            s = p.points[0]
            starts.append([s.x, s.y, 0])
            # Compatibility coordinates: x,y,placeholder-direction,tick,placeholder-action.
            path_segments = [f"{pt.x},{pt.y},0,{t},F" for t, pt in enumerate(p.points)]
            actual_paths.append(";".join(path_segments))
        else:
            starts.append([0, 0, 0])
            actual_paths.append("")

    return {
        "actionModel": "MAPF_POST",
        "mapFile": map_name,
        "teamSize": team_size,
        "gridWidth": width,
        "gridHeight": height,
        "start": starts,
        "actualPaths": actual_paths,
        "numTaskFinished": team_size,
    }
