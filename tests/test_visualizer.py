from __future__ import annotations

import tempfile
from pathlib import Path

from mapf.analytics.visualizer import export_trajectory_html, export_trajectory_svg
from mapf.core.models import Path as AgentPath
from mapf.core.models import Point
from mapf.solvers.base import MAPFSolution


def test_trajectory_visualizers() -> None:
    paths = {
        "agent_0": AgentPath(points=[Point(x=0, y=0), Point(x=0, y=1), Point(x=1, y=1)]),
        "agent_1": AgentPath(points=[Point(x=3, y=3), Point(x=2, y=3), Point(x=1, y=3)]),
    }
    sol = MAPFSolution(
        solver_name="TestSolver",
        is_centralized=False,
        success=True,
        paths=paths,
        makespan=3,
        sum_of_costs=6,
        runtime_ms=12.5,
    )
    obstacles = {Point(x=2, y=2)}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_svg = Path(tmpdir) / "test.svg"
        tmp_html = Path(tmpdir) / "test.html"

        res_svg = export_trajectory_svg(sol, grid_width=4, grid_height=4, obstacles=obstacles, out_path=tmp_svg)
        assert res_svg.exists()
        svg_content = res_svg.read_text(encoding="utf-8")
        assert "<svg" in svg_content
        assert "<polyline" in svg_content
        assert 'fill="#2b2b2b"' in svg_content  # Obstacle

        res_html = export_trajectory_html(sol, grid_width=4, grid_height=4, obstacles=obstacles, out_path=tmp_html)
        assert res_html.exists()
        html_content = res_html.read_text(encoding="utf-8")
        assert "<canvas" in html_content
        assert "TestSolver" in html_content
        assert "makespan" in html_content
