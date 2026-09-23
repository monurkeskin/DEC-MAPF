"""Exercise runnable examples; the subclass sketch only initializes an agent."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("script", "expected_output"),
    [
        (
            "01_basic_simulation.py",
            ("Success:                  True", "Independently valid:      True"),
        ),
        ("02_custom_negotiation_agent.py", ("Successfully initialized",)),
        (
            "03_centralized_vs_decentralized.py",
            ("Comparison Results:", "Both independently solved:  True"),
        ),
    ],
    ids=["basic-simulation", "custom-agent-initialization", "method-comparison"],
)
def test_teaching_example_delivers_its_documented_outcome(script, expected_output):
    res = subprocess.run(
        [sys.executable, f"examples/{script}"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    for expected in expected_output:
        assert expected in res.stdout, res.stdout


def test_registered_solver_runs_in_spawned_worker_and_exports_checked_bundle(
    tmp_path,
) -> None:
    from mapf.application.runs import digest

    command = [
        sys.executable,
        "examples/05_registered_solver_study.py",
        "--workspace",
        str(tmp_path),
    ]
    first = subprocess.run(
        command, capture_output=True, text=True, timeout=30, check=False
    )
    assert first.returncode == 0, first.stdout + first.stderr
    rows = json.loads((tmp_path / "all-trials.json").read_text())
    assert len(rows) == 1
    assert rows[0]["solver_id"] == "TutorialCBS"
    assert rows[0]["validation_status"] == "valid_solution"
    bundle = json.loads(next(tmp_path.glob("*.bundle.json")).read_text())
    assert digest(bundle["payload"]) == bundle["sha256"]
    assert bundle["payload"]["result"]["validation"]["is_valid"]
    again = subprocess.run(
        [*command, "--resume"], capture_output=True, text=True, timeout=30, check=False
    )
    assert again.returncode == 0, again.stdout + again.stderr
    resumed = json.loads((tmp_path / "all-trials.json").read_text())
    assert [(r["job_id"], r["attempt_count"]) for r in resumed] == [
        (rows[0]["job_id"], 1)
    ]
