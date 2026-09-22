"""Runnable examples test suite (C02).

Exercises actual integrations; the historical subclass example only initializes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_example_01_basic_simulation() -> None:
    path = Path("examples/01_basic_simulation.py")
    res = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Example 01 failed: {res.stderr}"
    assert "Success:" in res.stdout


def test_example_02_custom_negotiation_agent() -> None:
    path = Path("examples/02_custom_negotiation_agent.py")
    res = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Example 02 failed: {res.stderr}"
    assert "Successfully initialized" in res.stdout


def test_example_03_centralized_vs_decentralized() -> None:
    path = Path("examples/03_centralized_vs_decentralized.py")
    res = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Example 03 failed: {res.stderr}"
    assert "Comparison Results:" in res.stdout


def test_registered_solver_runs_in_spawned_worker_and_exports_checked_bundle(tmp_path) -> None:
    from mapf.application.runs import digest
    command = [sys.executable, "examples/05_registered_solver_study.py", "--workspace", str(tmp_path)]
    first = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    rows = json.loads((tmp_path / "all-trials.json").read_text())
    assert len(rows) == 1
    assert rows[0]["solver_id"] == "TutorialCBS"
    assert rows[0]["validation_status"] == "valid_solution"
    bundle = json.loads(next(tmp_path.glob("*.bundle.json")).read_text())
    assert digest(bundle["payload"]) == bundle["sha256"]
    assert bundle["payload"]["result"]["validation"]["is_valid"]
    again = subprocess.run([*command, "--resume"], capture_output=True, text=True, timeout=30, check=False)
    assert again.returncode == 0, again.stdout + again.stderr
    resumed = json.loads((tmp_path / "all-trials.json").read_text())
    assert [(r["job_id"], r["attempt_count"]) for r in resumed] == [(rows[0]["job_id"], 1)]
