from __future__ import annotations

import json
from html import escape
from pathlib import Path

from mapf.analytics._html_templates import render_template
from mapf.core.models import Point
from mapf.solvers.base import MAPFSolution


def export_trajectory_svg(
    solution: MAPFSolution,
    grid_width: int,
    grid_height: int,
    obstacles: set[Point],
    out_path: str | Path = "trajectory.svg",
    cell_size: int = 24,
) -> Path:
    """Write grid geometry and supplied trajectories as a vector SVG."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    width_px = grid_width * cell_size
    height_px = grid_height * cell_size

    # Distinct high-contrast palette
    palette = [
        "#e41a1c",
        "#377eb8",
        "#4daf4a",
        "#984ea3",
        "#ff7f00",
        "#ffff33",
        "#a65628",
        "#f781bf",
        "#999999",
        "#17becf",
    ]

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px} {height_px}" width="{width_px}" height="{height_px}">',
        f'  <rect width="{width_px}" height="{height_px}" fill="#ffffff" stroke="#cccccc" />',
    ]

    # Grid lines
    for x in range(grid_width + 1):
        svg_lines.append(
            f'  <line x1="{x * cell_size}" y1="0" x2="{x * cell_size}" y2="{height_px}" stroke="#f0f0f0" stroke-width="1" />'
        )
    for y in range(grid_height + 1):
        svg_lines.append(
            f'  <line x1="0" y1="{y * cell_size}" x2="{width_px}" y2="{y * cell_size}" stroke="#f0f0f0" stroke-width="1" />'
        )

    # Obstacles
    for obs in sorted(obstacles, key=lambda p: (p.y, p.x)):
        svg_lines.append(
            f'  <rect x="{obs.x * cell_size}" y="{obs.y * cell_size}" width="{cell_size}" height="{cell_size}" fill="#2b2b2b" />'
        )

    # Agent Paths
    for idx, (agent_id, path) in enumerate(sorted(solution.paths.items())):
        if not path.points:
            continue
        color = palette[idx % len(palette)]
        pts_str = " ".join(
            f"{p.x * cell_size + cell_size / 2},{p.y * cell_size + cell_size / 2}"
            for p in path.points
        )
        svg_lines.append(
            f'  <polyline points="{pts_str}" fill="none" stroke="{color}" stroke-width="2.5" stroke-opacity="0.8" stroke-linecap="round" />'
        )

        # Start marker (filled circle)
        s = path.points[0]
        svg_lines.append(
            f'  <circle cx="{s.x * cell_size + cell_size / 2}" cy="{s.y * cell_size + cell_size / 2}" r="{cell_size * 0.35}" fill="{color}" />'
        )
        # Goal marker (concentric ring)
        g = path.points[-1]
        svg_lines.append(
            f'  <circle cx="{g.x * cell_size + cell_size / 2}" cy="{g.y * cell_size + cell_size / 2}" r="{cell_size * 0.4}" fill="none" stroke="{color}" stroke-width="2" />'
        )

    svg_lines.append("</svg>")
    out.write_text("\n".join(svg_lines), encoding="utf-8")
    return out


def export_trajectory_html(
    solution: MAPFSolution,
    grid_width: int,
    grid_height: int,
    obstacles: set[Point],
    out_path: str | Path = "trajectory_viewer.html",
) -> Path:
    """Write a standalone Canvas player with no external browser dependencies.

    This compatibility viewer holds each path at its last cell. Use the application
    replay export for setting-aware disappearance and recorded decision layers.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    agent_data: dict[str, list[list[int]]] = {
        aid: [[p.x, p.y] for p in path.points] for aid, path in solution.paths.items()
    }
    obs_data = [[p.x, p.y] for p in obstacles]

    html_content = render_template(
        "trajectory.html",
        {
            "solver_name": escape(solution.solver_name),
            "agent_count": len(solution.paths),
            "makespan": solution.makespan,
            "sum_of_costs": solution.sum_of_costs,
            "runtime_ms": format(solution.runtime_ms, ".2f"),
            "status_color": "#4ade80" if solution.success else "#f87171",
            "status_text": "Solved" if solution.success else "Failed",
            "grid_width": grid_width,
            "grid_height": grid_height,
            "obstacles": json.dumps(obs_data),
            "paths": json.dumps(agent_data).replace("<", r"\u003c"),
        },
    )
    out.write_text(html_content, encoding="utf-8")
    return out
