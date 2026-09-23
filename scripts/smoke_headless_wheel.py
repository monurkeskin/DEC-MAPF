"""Source-free, core-only installed-wheel batch execution qualification."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", action="store_true", help="Qualify the optional OS resource probe")
    args = parser.parse_args()
    import mapf
    from mapf.application.diagnostics import diagnose
    from mapf.application.experiments import ExperimentService, compile_experiment
    from mapf.application.resources import ResourcePolicy, SystemResourceProbe
    from mapf.application.runs import RunRepository

    assert "site-packages" in Path(mapf.__file__).parts, mapf.__file__
    assert importlib.util.find_spec("fastapi") is None, (
        "This receipt requires a headless environment without the GUI extra"
    )
    if not args.resources:
        assert importlib.util.find_spec("psutil") is None
        try:
            SystemResourceProbe()
        except ValueError as error:
            assert "resources extra" in str(error)
        else:
            raise AssertionError("Missing optional probe dependency was silently accepted")
    spec = {
        "name": "installed core headless smoke",
        "scenarios": [{"scenario_id": "crossing-2a"}],
        "defaults": {
            "solver_id": "Decentralized-HeatMap",
            "timeout_sec": None,
            "negotiation_deadline_sec": 60,
        },
        "matrix": {"setting": ["SETTING_2", "SETTING_4"]},
        "budget": {"workers": 2, "wall_seconds": 30, "max_trials": 2, "disk_mb": 128},
    }
    if args.resources:
        # These tiny fixtures use an explicit smoke policy, not article defaults
        # or a claim about memory required by arbitrary centralized searches.
        spec["budget"]["resources"] = ResourcePolicy(
            optimal_reserve_mb=128, decentralized_reserve_mb=128,
            free_memory_mb=64, max_cpu_percent=100, idle_timeout_sec=10,
        ).model_dump()
        spec["defaults"]["timeout_sec"] = 15
        spec["matrix"] = {"solver_id": ["CBS", "Decentralized-HeatMap"]}
    manifest = compile_experiment(spec)
    assert manifest["provenance"]["git_commit"] == "unavailable"
    assert manifest["provenance"]["working_tree_dirty"] is None
    assert manifest["provenance"]["source_origin"] == "installed-package"
    with tempfile.TemporaryDirectory(prefix="mapf-core-only-") as directory:
        service = ExperimentService(RunRepository(directory))
        doctor = diagnose(workspace=directory, required=["resources"] if args.resources else [])
        assert doctor["status"] == "ok", doctor
        assert doctor["package_version"] == mapf.__version__, doctor
        assert not doctor["components"]["gui"]["available"]
        result = service.execute(manifest)
        assert result["planned"] == result["successful"] == 2, result
        rows = service.rows(manifest["experiment_id"])
        assert all(r["validation_status"] == "valid_solution" for r in rows)
        for job in service.repository.list_jobs():
            run = service.repository.get_run(job["run_id"], include_frames=False)
            assert run["metadata"]["execution_thread_limits"]
            assert set(run["metadata"]["execution_thread_limits"].values()) == {"1"}
            if args.resources:
                receipt = run["metadata"]["resource_admission"]
                assert receipt["observation"]["available_bytes"] > 0
                assert receipt["observation"]["cpu_percent"] is not None
                assert receipt["observation"]["error"] is None
        before = [job["job_id"] for job in service.repository.list_jobs()]
        assert service.execute(manifest, resume=True)["successful"] == 2
        assert [job["job_id"] for job in service.repository.list_jobs()] == before
        assert "fastapi" not in sys.modules and "mapf.gui.app" not in sys.modules
        print(
            json.dumps(
                {
                    "status": "passed",
                    "python": sys.version,
                    "module": mapf.__file__,
                    "fastapi_installed": False,
                    "resource_admission": args.resources,
                    "doctor": doctor,
                    "completed_resume_preserved": True,
                    "source_sha256": manifest["source_sha256"],
                    "result": result,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
