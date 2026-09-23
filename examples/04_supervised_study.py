"""Run a small durable study through the same service as ``mapf batch``.

No GUI dependencies are imported. Run as a script (not an unguarded notebook
cell), because workers use multiprocessing spawn.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mapf.application.experiments import ExperimentService, compile_experiment
from mapf.application.runs import RunRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("runs/python-study"))
    args = parser.parse_args()
    spec = {
        "name": "Supervised Python teaching example",
        "scenarios": [{"scenario_id": "crossing-2a"}],
        "defaults": {"setting": "SETTING_4", "max_steps": 40, "timeout_sec": 10,
                     "recording_level": "full-trace", "initial_tokens": 5, "fov_size": 5},
        "matrix": {"solver_id": ["Decentralized-HeatMap", "CBS"]},
        "budget": {"workers": 1, "wall_seconds": 60, "max_trials": 2, "disk_mb": 128},
        "sampling": {"population": "One teaching fixture", "independent_unit": "scenario"},
    }
    manifest = compile_experiment(spec)
    repository = RunRepository(args.workspace)
    service = ExperimentService(repository)
    # Explicitly refuse accidental reuse; use the CLI resume command if intended.
    if any(item["experiment_id"] == manifest["experiment_id"] for item in service.manifests()):
        raise SystemExit("Study already exists: use an explicit resume or a new --workspace.")
    (args.workspace / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    summary = service.execute(manifest)
    rows = service.rows(manifest["experiment_id"])
    (args.workspace / "all-trials.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    for row in rows:
        print(json.dumps({key: row[key] for key in (
            "solver_id", "state", "validation_status", "success", "sum_of_costs", "run_id"
        )}))
    return 0 if summary["state"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
