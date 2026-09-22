"""Standalone diagnostics HTML renderer, included in wheels."""

from __future__ import annotations

from pathlib import Path
from typing import Any


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
    """Render a modern, responsive, zero-dependency standalone HTML dashboard."""
    # Build SVG Grid for Hotspots
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

    # Format Concession Table
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

    # Format Choke points Table
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

    # Format Rejection Reasons Table
    rejection_rows = []
    for reason, count in rejection_data.get("breakdown", {}).items():
        rejection_rows.append(
            f"<tr><td><code>{reason}</code></td><td><strong>{count}</strong></td></tr>"
        )
    rejection_table = (
        "".join(rejection_rows)
        if rejection_rows
        else "<tr><td colspan='2'>Zero negotiation failures</td></tr>"
    )

    # Provenance Badges
    git_commit = manifest.get("git_commit", "N/A")
    seed_val = manifest.get("random_seed", "N/A")
    setting_name = manifest.get("setting", "N/A")
    commit_type = manifest.get("commitment", "N/A")
    agent_count = manifest.get("agent_count", "N/A")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Deep MAPF Diagnostics: {run_id}</title>
    <style>
        :root {{
            --bg: #0b0f19;
            --card: #151c2e;
            --accent: #38bdf8;
            --text: #f1f5f9;
            --muted: #94a3b8;
            --border: #334155;
            --success: #10b981;
            --danger: #ef4444;
            --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        body {{
            margin: 0;
            padding: 30px;
            background: var(--bg);
            color: var(--text);
            font-family: var(--font);
            line-height: 1.5;
        }}
        .header {{
            margin-bottom: 25px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 15px;
        }}
        h1 {{ margin: 0 0 5px 0; font-size: 24px; color: var(--accent); }}
        .badge {{ background: #1e293b; color: var(--accent); padding: 3px 8px; border-radius: 4px; font-size: 12px; font-family: monospace; margin-right: 5px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px; }}
        .metric-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 15px; }}
        .metric-title {{ font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }}
        .metric-val {{ font-size: 24px; font-weight: bold; margin-top: 5px; color: #fff; }}
        .main-layout {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
        .panel {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }}
        .panel h2 {{ margin-top: 0; font-size: 16px; color: var(--text); border-bottom: 1px solid var(--border); padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }}
        th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #1e293b; }}
        th {{ color: var(--muted); font-weight: 600; }}
        @media (max-width: 900px) {{ .main-layout {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <div class="header">
        <h1>DEC-MAPF: Deep Diagnostics & Provenance</h1>
        <div style="margin-top: 8px;">
            Run: <span class="badge">{run_id}</span>
            Setting: <span class="badge">{setting_name}</span>
            Commitment: <span class="badge">{commit_type}</span>
            Agents: <span class="badge">k={agent_count}</span>
            Seed: <span class="badge">{seed_val}</span>
            Commit: <span class="badge">{git_commit}</span>
        </div>
    </div>

    <div class="grid">
        <div class="metric-card">
            <div class="metric-title">Token Wealth Gini</div>
            <div class="metric-val">{gini_data.get("gini_coefficient") if gini_data.get("gini_coefficient") is not None else "Unavailable"}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Total Conflicts</div>
            <div class="metric-val">{hotspots.get("total_conflicts", 0)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Negotiation Success Rate</div>
            <div class="metric-val">{rejection_data.get("success_rate", 1.0) * 100:.1f}%</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Mean Agent Wait Ratio</div>
            <div class="metric-val">{wait_data.get("mean_wait_ratio", 0.0) * 100:.1f}%</div>
        </div>
        <div class="metric-card">
            <div class="metric-title">Saved Keyframes</div>
            <div class="metric-val">{len(keyframes)}</div>
        </div>
    </div>

    <div class="main-layout">
        <div class="panel">
            <h2>Spatial Congestion Hotspot Heatmap</h2>
            <div style="display: flex; justify-content: center; margin: 15px 0;">
                {svg_markup}
            </div>
            <table>
                <thead><tr><th>Choke Coordinate</th><th>Conflict Density</th></tr></thead>
                <tbody>{choke_table}</tbody>
            </table>
        </div>

        <div class="panel">
            <h2>Bilateral Concession Dynamics</h2>
            <table>
                <thead><tr><th>Round</th><th>Offered Utility</th><th>Std Dev</th></tr></thead>
                <tbody>{concession_table}</tbody>
            </table>

            <h2 style="margin-top: 30px;">Cognitive Rejection & Impasse Breakdown</h2>
            <table>
                <thead><tr><th>Failure Reason</th><th>Occurrences</th></tr></thead>
                <tbody>{rejection_table}</tbody>
            </table>

            <h2 style="margin-top: 30px;">Token Balance Distribution</h2>
            <div style="margin-top: 10px; font-size: 13px; color: var(--muted);">
                Min Tokens: <strong>{gini_data.get("min_tokens", 5)}</strong> |
                Max Tokens: <strong>{gini_data.get("max_tokens", 5)}</strong> |
                Mean Tokens: <strong>{gini_data.get("mean_tokens", 5.0):.2f}</strong>
            </div>
        </div>
    </div>
</body>
</html>
"""
    output_html_path.write_text(html_content, encoding="utf-8")
    print(
        f"  [Report] Successfully generated interactive HTML report: {output_html_path}"
    )
