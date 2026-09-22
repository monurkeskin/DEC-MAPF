from __future__ import annotations

import math
import random
from typing import Any

from mapf.core.models import Point


def parse_movingai_map(content: str) -> tuple[int, int, set[Point]]:
    """Parse MovingAI .map format (Stern et al. 2019b).

    Returns:
        tuple of (width, height, set of obstacle Points)
    """
    lines = content.strip().splitlines()
    if len(lines) < 5 or lines[0].strip() != "type octile":
        raise ValueError("MovingAI map must begin with type octile and a complete header")
    width = 0
    height = 0
    map_start_idx = 0

    for i, line in enumerate(lines):
        line_clean = line.strip()
        if line_clean.startswith("width"):
            width = int(line_clean.split()[1])
        elif line_clean.startswith("height"):
            height = int(line_clean.split()[1])
        elif line_clean.startswith("map"):
            map_start_idx = i + 1
            break

    obstacles: set[Point] = set()
    grid_lines = lines[map_start_idx:]
    if width < 1 or height < 1 or len(grid_lines) != height or any(len(row) != width for row in grid_lines):
        raise ValueError("MovingAI map dimensions do not match its rectangular body")
    if any(char not in ".GS@TOW" for row in grid_lines for char in row):
        raise ValueError("Unsupported MovingAI terrain symbol")

    for y, row in enumerate(grid_lines):
        if y >= height:
            break
        for x, char in enumerate(row):
            if x >= width:
                break
            # In MovingAI, '@' and 'T' denote impassable obstacles, '.' is traversable
            if char in ("@", "T", "O", "W"):
                obstacles.add(Point(x=x, y=y))

    return width, height, obstacles


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


def generate_benchmark_map(
    width: int,
    height: int,
    obstacle_density: float = 0.0,
    seed: int = 42,
) -> set[Point]:
    """Generate a synthetic, uniformly sampled obstacle map, not a MovingAI import.

    Examples from JAAMAS 2024:
    - empty-16-16: obstacle_density = 0.0
    - empty-32-32: obstacle_density = 0.0
    - random-32-32-10: obstacle_density = 0.10
    - random-32-32-20: obstacle_density = 0.20
    """
    if width < 1 or height < 1 or not 0 <= obstacle_density < 1:
        raise ValueError("Positive dimensions and obstacle density in [0,1) required")
    if obstacle_density == 0.0:
        return set()

    rng = random.Random(seed)
    total_cells = width * height
    num_obstacles = int(total_cells * obstacle_density)

    all_coords = [Point(x=x, y=y) for x in range(width) for y in range(height)]
    obstacles = set(rng.sample(all_coords, num_obstacles))
    return obstacles


def generate_stern_scenario(
    width: int,
    height: int,
    obstacles: set[Point],
    num_agents: int,
    min_dist: int = 4,
    max_dist: int = 24,
    seed: int = 42,
    max_attempts: int = 5000,
) -> list[tuple[Point, Point]]:
    """Sample synthetic reachable start/goal pairs without relaxing requested bounds.

    Explicit sampling constraints (not a claim of the historical Java distribution):
    1. Neither start nor destination can be an obstacle.
    2. Unique start points across all agents.
    3. Unique destination points across all agents.
    4. Start points are not immediately coincident.
    5. Manhattan distance between start and destination is in [min_dist, max_dist] (JAAMAS: 4-24).
    """
    rng = random.Random(seed)
    if width < 1 or height < 1 or num_agents < 1 or not 0 <= min_dist <= max_dist:
        raise ValueError("Invalid synthetic scenario dimensions, agent count or distance range")
    traversable = [
        Point(x=x, y=y)
        for x in range(width)
        for y in range(height)
        if Point(x=x, y=y) not in obstacles
    ]

    if len(traversable) < num_agents:
        raise ValueError(
            f"Not enough traversable cells ({len(traversable)}) for {num_agents} agents on {width}x{height} grid."
        )

    # Compute 4-connected components across traversable cells (B13)
    component_map: dict[Point, int] = {}
    current_comp = 0
    traversable_set = set(traversable)

    for pt in traversable:
        if pt in component_map:
            continue
        current_comp += 1
        queue = [pt]
        component_map[pt] = current_comp
        for curr in queue:
            for nxt in curr.get_neighbors(allow_wait=False):
                if nxt in traversable_set and nxt not in component_map:
                    component_map[nxt] = current_comp
                    queue.append(nxt)

    starts: set[Point] = set()
    goals: set[Point] = set()
    pairs: list[tuple[Point, Point]] = []

    attempts = 0
    while len(pairs) < num_agents and attempts < max_attempts:
        attempts += 1
        s = rng.choice(traversable)
        if s in starts:
            continue

        g = rng.choice(traversable)
        if g in goals or g == s:
            continue

        # Must reside in identical connected component (B13)
        if component_map.get(s) != component_map.get(g):
            continue

        dist = s.manhattan_distance(g)
        if min_dist <= dist <= max_dist:
            starts.add(s)
            goals.add(g)
            pairs.append((s, g))

    if len(pairs) < num_agents:
        raise ValueError(
            f"Could not sample {num_agents} mutually reachable pairs within distance range "
            f"[{min_dist}, {max_dist}] after {max_attempts} attempts. Only {len(pairs)} pairs found."
        )

    return pairs


def parse_movingai_scen(content: str) -> list[tuple[Point, Point]]:
    """Parse MovingAI .scen format (Nathan Sturtevant & Stern et al. 2019b).

    Format per line:
    bucket <tab> map_file <tab> width <tab> height <tab> start_x <tab> start_y <tab> goal_x <tab> goal_y <tab> optimal_length

    Returns:
        List of (start_point, goal_point) tuples.
    """
    lines = content.strip().splitlines()
    if not lines or lines[0].strip() != "version 1":
        raise ValueError("MovingAI scenario header must be version 1")
    pairs: list[tuple[Point, Point]] = []

    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith(("version", "#")):
            continue

        parts = line_clean.split()
        if len(parts) != 9:
            raise ValueError("MovingAI scenario rows require nine columns")
        if len(parts) == 9:
            # MovingAI format indices:
            # parts[4] = start_x, parts[5] = start_y
            # parts[6] = goal_x,  parts[7] = goal_y
            try:
                start_x = int(parts[4])
                start_y = int(parts[5])
                goal_x = int(parts[6])
                goal_y = int(parts[7])
                width, height = int(parts[2]), int(parts[3])
                distance = float(parts[8])
                if (width < 1 or height < 1 or not math.isfinite(distance) or distance < 0
                    or not 0 <= start_x < width or not 0 <= goal_x < width
                    or not 0 <= start_y < height or not 0 <= goal_y < height):
                    raise ValueError("Scenario coordinates/distance violate the declared map")
                pairs.append((Point(x=start_x, y=start_y), Point(x=goal_x, y=goal_y)))
            except ValueError:
                raise ValueError("Malformed MovingAI scenario row") from None

    return pairs


def format_movingai_scen(
    pairs: list[tuple[Point, Point]],
    map_name: str,
    width: int,
    height: int,
) -> str:
    """Format start-goal pairs into standard MovingAI .scen format."""
    lines = ["version 1"]
    for idx, (s, g) in enumerate(pairs):
        bucket = idx % 10
        dist = s.manhattan_distance(g)
        lines.append(
            f"{bucket}\t{map_name}\t{width}\t{height}\t{s.x}\t{s.y}\t{g.x}\t{g.y}\t{dist:.8f}"
        )
    return "\n".join(lines) + "\n"


def export_standard_paths(solution_paths: dict[str, Any]) -> str:
    """Export agent trajectories to canonical MAPF format.

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
    """Export trajectory solution to League of Robot Runners / PlanViz JSON structure."""
    agent_names = sorted(solution_paths.keys())
    team_size = len(agent_names)

    starts: list[list[int]] = []
    actual_paths: list[str] = []

    for name in agent_names:
        p = solution_paths[name]
        if p.points:
            s = p.points[0]
            starts.append([s.x, s.y, 0])
            # PlanViz string format: "x,y,dir,time,action;..."
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
