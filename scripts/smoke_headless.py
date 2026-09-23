"""Source-free, core-only installed-wheel batch execution qualification."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


def main() -> None:
    import mapf
    from mapf.application.experiments import ExperimentService, compile_experiment
    from mapf.application.runs import RunRepository
    assert "site-packages" in Path(mapf.__file__).parts, mapf.__file__
    assert importlib.util.find_spec("fastapi") is None, "This receipt requires the core-only environment"
    spec = {"name": "installed core headless smoke", "scenarios": [{"scenario_id": "crossing-2a"}],
            "defaults": {"solver_id": "CBS", "timeout_sec": 10},
            "matrix": {"setting": ["SETTING_2", "SETTING_4"]},
            "budget": {"workers": 2, "wall_seconds": 30, "max_trials": 2, "disk_mb": 128}}
    manifest = compile_experiment(spec)
    with tempfile.TemporaryDirectory(prefix="mapf-core-only-") as directory:
        service = ExperimentService(RunRepository(directory))
        result = service.execute(manifest)
        assert result["planned"] == result["successful"] == 2, result
        rows = service.rows(manifest["experiment_id"])
        assert all(r["validation_status"] == "valid_solution" for r in rows)
        for job in service.repository.list_jobs():
            run = service.repository.get_run(job["run_id"], include_frames=False)
            assert run["metadata"]["execution_thread_limits"]
            assert set(run["metadata"]["execution_thread_limits"].values()) == {"1"}
        assert "fastapi" not in sys.modules and "mapf.gui.app" not in sys.modules
        print(json.dumps({"status": "passed", "python": sys.version, "module": mapf.__file__,
                          "fastapi_installed": False, "source_sha256": manifest["source_sha256"], "result": result}, indent=2))

if __name__ == "__main__":
    main()
