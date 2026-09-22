"""Register an existing method, then plan, spawn, validate and export it.

The alias uses the existing validated CBS implementation unchanged. It is an
extension-composition example, not a new solver or a scientific comparison.
Registration is at module scope so multiprocessing spawn repeats it in workers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mapf.api import (
    ExperimentService,
    MAPFSolverProtocol,
    RunRepository,
    compile_experiment,
    export_bundle,
    get_solver,
    register_solver,
)
from mapf.application.runs import atomic_write, encode


def existing_cbs(time_limit_sec: float = 60) -> MAPFSolverProtocol:
    """Compose an existing registered method; keep its implementation unchanged."""
    return get_solver("CBS", time_limit_sec=time_limit_sec)

register_solver(
    "TutorialCBS", is_centralized=True,
    description="Teaching alias of the existing CBS method; no algorithm modification",
    constructor_inputs=(("timeout_sec", "time_limit_sec"),),
)(existing_cbs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("runs/registered-study"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    repo = RunRepository(args.workspace)
    service = ExperimentService(repo)
    manifest_file = args.workspace / "input-manifest.json"
    if args.resume:
        manifest = json.loads(manifest_file.read_text())
    else:
        if manifest_file.exists():
            raise SystemExit("Use --resume or a fresh workspace; original evidence is preserved.")
        manifest = compile_experiment({
            "name": "Existing solver registration and worker composition",
            "scenarios": [{"scenario_id": "crossing-2a"}],
            "defaults": {"solver_id": "TutorialCBS", "setting": "SETTING_4",
                         "timeout_sec": 10, "recording_level": "full-trace"},
            "budget": {"workers": 1, "wall_seconds": 30, "max_trials": 1},
            "sampling": {"population": "one teaching fixture", "generalization": "none"},
        })
        atomic_write(manifest_file, encode(manifest))
    summary = service.execute(manifest, resume=args.resume)
    rows = service.rows(manifest["experiment_id"])
    atomic_write(args.workspace / "all-trials.json", encode(rows))
    for row in rows:
        if row["state"] == "completed":
            payload = repo.get_run(row["run_id"])
            assert payload is not None
            atomic_write(args.workspace / f"{row['run_id']}.bundle.json", encode(export_bundle(payload)))
    print(json.dumps(summary, indent=2))
    return 0 if summary["successful"] == summary["planned"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
