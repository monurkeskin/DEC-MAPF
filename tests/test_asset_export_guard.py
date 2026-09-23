"""Retired plot commands must not publish unqualified aggregates."""

import subprocess
import sys
from pathlib import Path


def test_retired_plotter_refuses_before_reading_or_writing_results(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/render_modern_assets.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    assert result.returncode != 0
    assert "mapf batch export/analyze" in result.stderr
    assert list(tmp_path.iterdir()) == []
