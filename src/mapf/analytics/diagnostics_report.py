"""Standalone diagnostics HTML renderer, included in wheels."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from mapf.analytics._html_templates import render_template


def format_metric(value: float | None, spec: str = "") -> str:
    """Use the same missing-data label in CLI and HTML diagnostics."""
    return "Unavailable" if value is None else format(value, spec)


def _text(value: object) -> str:
    return escape(str(value))


def hotspot_svg(hotspots: dict[str, Any], grid_width: int, grid_height: int) -> str:
    cell_size = max(12, min(24, 600 // max(grid_width, grid_height)))
    svg_w = grid_width * cell_size
    svg_h = grid_height * cell_size

    max_conflicts = max(
        (cp["conflicts"] for cp in hotspots.get("top_chokepoints", [])),
        default=1,
    )

    svg_cells: list[str] = []
    matrix = hotspots["density_matrix"]
    for y in range(grid_height):
        for x in range(grid_width):
            c_val = matrix[y][x]
            intensity = min(1.0, c_val / float(max(1, max_conflicts)))
            if intensity > 0:
                # Color gradient from bright yellow to deep red
                r = 255
                g = int(220 * (1.0 - intensity * 0.8))
                b = int(50 * (1.0 - intensity))
                fill = f"rgb({r},{g},{b})"
                opacity = 0.3 + 0.7 * intensity
            else:
                fill = "#1a1f2c"
                opacity = 0.5

            svg_cells.append(
                f'<rect x="{x * cell_size}" y="{y * cell_size}" '
                f'width="{cell_size - 1}" height="{cell_size - 1}" '
                f'fill="{fill}" fill-opacity="{opacity}" rx="2">'
                f"<title>Cell ({x}, {y}): {c_val} conflicts</title></rect>"
            )

    svg_markup = f"""
    <svg width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}" style="border: 1px solid #334155; border-radius: 8px; background: #0f172a;">
        {"".join(svg_cells)}
    </svg>
    """
    return svg_markup


def concession_rows(concessions: dict[str, Any]) -> str:
    concession_rows = []
    for r, u, s in zip(
        concessions.get("rounds", []),
        concessions.get("mean_utility", []),
        concessions.get("std_utility", []),
    ):
        concession_rows.append(
            f"<tr><td>Round {r}</td><td><strong>{u:.4f}</strong></td><td>±{s:.4f}</td></tr>"
        )
    concession_table = (
        "".join(concession_rows)
        if concession_rows
        else "<tr><td colspan='3'>No multi-round concessions</td></tr>"
    )
    return concession_table


def chokepoint_rows(hotspots: dict[str, Any]) -> str:
    choke_rows = []
    for cp in hotspots.get("top_chokepoints", [])[:8]:
        choke_rows.append(
            f"<tr><td>({cp['x']}, {cp['y']})</td><td><strong>{cp['conflicts']}</strong></td></tr>"
        )
    choke_table = (
        "".join(choke_rows)
        if choke_rows
        else "<tr><td colspan='2'>No conflicts</td></tr>"
    )
    return choke_table


def rejection_rows(rejection_data: dict[str, Any]) -> str:
    rejection_rows = []
    for reason, count in rejection_data.get("breakdown", {}).items():
        rejection_rows.append(
            f"<tr><td><code>{_text(reason)}</code></td><td><strong>{_text(count)}</strong></td></tr>"
        )
    rejection_table = (
        "".join(rejection_rows)
        if rejection_rows
        else "<tr><td colspan='2'>No failure reasons recorded</td></tr>"
    )
    if not rejection_data.get("total_sessions"):
        rejection_table = (
            "<tr><td colspan='2'>No negotiation sessions recorded</td></tr>"
        )
    return rejection_table


def generate_html_report(
    run_id: str,
    manifest: dict[str, Any],
    hotspots: dict[str, Any],
    concessions: dict[str, Any],
    gini_data: dict[str, Any],
    wait_data: dict[str, Any],
    rejection_data: dict[str, Any],
    keyframes: list[dict[str, Any]],
    grid_width: int,
    grid_height: int,
    output_html_path: Path,
) -> None:
    """Render a self-contained HTML report from the supplied diagnostic summaries."""
    run_id = _text(run_id)
    git_commit = _text(manifest.get("git_commit", "N/A"))
    seed_val = _text(manifest.get("random_seed", "N/A"))
    setting_name = _text(manifest.get("setting", "N/A"))
    commit_type = _text(manifest.get("commitment", "N/A"))
    agent_count = _text(manifest.get("agent_count", "N/A"))

    html_content = render_template(
        "diagnostics.html",
        {
            "run_id": run_id,
            "setting_name": setting_name,
            "commit_type": commit_type,
            "agent_count": agent_count,
            "seed_val": seed_val,
            "git_commit": git_commit,
            "gini": format_metric(gini_data.get("gini_coefficient")),
            "total_conflicts": hotspots.get("total_conflicts", 0),
            "success_rate": format_metric(rejection_data.get("success_rate"), ".1%"),
            "wait_ratio": format_metric(wait_data.get("mean_wait_ratio"), ".1%"),
            "keyframes": len(keyframes),
            "svg_markup": hotspot_svg(hotspots, grid_width, grid_height),
            "choke_table": chokepoint_rows(hotspots),
            "concession_table": concession_rows(concessions),
            "rejection_table": rejection_rows(rejection_data),
            "min_tokens": format_metric(gini_data.get("min_tokens")),
            "max_tokens": format_metric(gini_data.get("max_tokens")),
            "mean_tokens": format_metric(gini_data.get("mean_tokens"), ".2f"),
        },
    )
    output_html_path.write_text(html_content, encoding="utf-8")
    print(
        f"  [Report] Successfully generated interactive HTML report: {output_html_path}"
    )
