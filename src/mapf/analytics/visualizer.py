from __future__ import annotations

import json
from pathlib import Path

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
    """Generate publication-ready vector SVG showing multi-agent trajectories."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    width_px = grid_width * cell_size
    height_px = grid_height * cell_size

    # Distinct high-contrast palette
    palette = [
        "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
        "#ffff33", "#a65628", "#f781bf", "#999999", "#17becf"
    ]

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_px} {height_px}" width="{width_px}" height="{height_px}">',
        f'  <rect width="{width_px}" height="{height_px}" fill="#ffffff" stroke="#cccccc" />',
    ]

    # Grid lines
    for x in range(grid_width + 1):
        svg_lines.append(f'  <line x1="{x * cell_size}" y1="0" x2="{x * cell_size}" y2="{height_px}" stroke="#f0f0f0" stroke-width="1" />')
    for y in range(grid_height + 1):
        svg_lines.append(f'  <line x1="0" y1="{y * cell_size}" x2="{width_px}" y2="{y * cell_size}" stroke="#f0f0f0" stroke-width="1" />')

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
    """Generate an interactive, zero-dependency standalone HTML5 canvas player."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    agent_data: dict[str, list[list[int]]] = {
        aid: [[p.x, p.y] for p in path.points]
        for aid, path in solution.paths.items()
    }
    obs_data = [[p.x, p.y] for p in obstacles]

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>DEC-MAPF - Trajectory Replay Viewer</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      margin: 0;
      padding: 24px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }}
    .container {{
      max-width: 900px;
      width: 100%;
      background: #1e293b;
      border-radius: 12px;
      padding: 24px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }}
    h1 {{
      margin-top: 0;
      font-size: 20px;
      font-weight: 600;
      color: #38bdf8;
      display: flex;
      justify-content: space-between;
    }}
    .stats-bar {{
      display: flex;
      gap: 16px;
      margin-bottom: 16px;
      font-size: 13px;
      color: #94a3b8;
    }}
    .stats-bar span strong {{
      color: #f8fafc;
    }}
    canvas {{
      background: #090d16;
      border: 1px solid #334155;
      border-radius: 8px;
      display: block;
      margin: 0 auto 16px auto;
    }}
    .controls {{
      display: flex;
      gap: 12px;
      align-items: center;
      justify-content: center;
      margin-top: 8px;
    }}
    button {{
      background: #38bdf8;
      color: #0f172a;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }}
    button:hover {{
      background: #0284c7;
    }}
    input[type=range] {{
      flex-grow: 1;
      max-width: 400px;
    }}
    .step-display {{
      font-family: monospace;
      font-size: 15px;
      min-width: 100px;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>
      <span>MAPF Trajectory Replay Viewer</span>
      <span>{solution.solver_name}</span>
    </h1>
    <div class="stats-bar">
      <span>Agents: <strong>{len(solution.paths)}</strong></span>
      <span>Makespan: <strong>{solution.makespan}</strong></span>
      <span>Sum of Costs: <strong>{solution.sum_of_costs}</strong></span>
      <span>Runtime: <strong>{solution.runtime_ms:.2f} ms</strong></span>
      <span>Status: <strong style="color: {'#4ade80' if solution.success else '#f87171'}">{'Solved' if solution.success else 'Failed'}</strong></span>
    </div>

    <canvas id="simCanvas" width="640" height="640"></canvas>

    <div class="controls">
      <button id="playBtn">Play</button>
      <button id="prevBtn">Prev</button>
      <input type="range" id="timeSlider" min="0" max="{solution.makespan}" value="0">
      <button id="nextBtn">Next</button>
      <span class="step-display">Tick: <strong id="tickLabel">0</strong> / {solution.makespan}</span>
    </div>
  </div>

  <script>
    const gridW = {grid_width};
    const gridH = {grid_height};
    const obstacles = {json.dumps(obs_data)};
    const paths = {json.dumps(agent_data)};
    const makespan = {solution.makespan};

    const canvas = document.getElementById('simCanvas');
    const ctx = canvas.getContext('2d');
    const slider = document.getElementById('timeSlider');
    const tickLabel = document.getElementById('tickLabel');
    const playBtn = document.getElementById('playBtn');

    const cellW = canvas.width / gridW;
    const cellH = canvas.height / gridH;

    const colors = [
      "#38bdf8", "#f43f5e", "#10b981", "#fbbf24", "#a855f7",
      "#06b6d4", "#f97316", "#84cc16", "#ec4899", "#6366f1"
    ];

    let currentTick = 0;
    let isPlaying = false;
    let playInterval = null;

    function render() {{
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw Grid Lines
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth = 1;
      for (let x = 0; x <= gridW; x++) {{
        ctx.beginPath();
        ctx.moveTo(x * cellW, 0);
        ctx.lineTo(x * cellW, canvas.height);
        ctx.stroke();
      }}
      for (let y = 0; y <= gridH; y++) {{
        ctx.beginPath();
        ctx.moveTo(0, y * cellH);
        ctx.lineTo(canvas.width, y * cellH);
        ctx.stroke();
      }}

      // Draw Obstacles
      ctx.fillStyle = '#334155';
      obstacles.forEach(([ox, oy]) => {{
        ctx.fillRect(ox * cellW, oy * cellH, cellW, cellH);
      }});

      // Draw Agent Trails and Positions
      let cIdx = 0;
      for (const [aid, pList] of Object.entries(paths)) {{
        const color = colors[cIdx % colors.length];
        cIdx++;

        // Trail up to currentTick
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        const maxIdx = Math.min(currentTick, pList.length - 1);
        for (let i = 0; i <= maxIdx; i++) {{
          const [px, py] = pList[i];
          const cx = px * cellW + cellW / 2;
          const cy = py * cellH + cellH / 2;
          if (i === 0) ctx.moveTo(cx, cy);
          else ctx.lineTo(cx, cy);
        }}
        ctx.stroke();

        // Current Position Circle
        if (pList.length > 0) {{
          const currPt = currentTick < pList.length ? pList[currentTick] : pList[pList.length - 1];
          const cx = currPt[0] * cellW + cellW / 2;
          const cy = currPt[1] * cellH + cellH / 2;

          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(cx, cy, Math.min(cellW, cellH) * 0.35, 0, Math.PI * 2);
          ctx.fill();

          ctx.fillStyle = '#0f172a';
          ctx.font = '10px sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(aid.replace('agent_', ''), cx, cy);
        }}
      }}

      tickLabel.innerText = currentTick;
      slider.value = currentTick;
    }}

    function setTick(t) {{
      currentTick = Math.max(0, Math.min(makespan, t));
      render();
    }}

    slider.addEventListener('input', (e) => {{
      setTick(parseInt(e.target.value));
    }});

    document.getElementById('prevBtn').addEventListener('click', () => {{
      setTick(currentTick - 1);
    }});

    document.getElementById('nextBtn').addEventListener('click', () => {{
      setTick(currentTick + 1);
    }});

    playBtn.addEventListener('click', () => {{
      isPlaying = !isPlaying;
      playBtn.innerText = isPlaying ? 'Pause' : 'Play';
      if (isPlaying) {{
        playInterval = setInterval(() => {{
          if (currentTick >= makespan) {{
            setTick(0);
          }} else {{
            setTick(currentTick + 1);
          }}
        }}, 300);
      }} else {{
        clearInterval(playInterval);
      }}
    }});

    render();
  </script>
</body>
</html>
"""
    out.write_text(html_content, encoding="utf-8")
    return out
