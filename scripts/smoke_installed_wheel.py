"""Run with the installed wheel's Python, from outside the source checkout.

An acceptance check, not a benchmark. Uses an isolated temporary workspace and a
real spawned solver, verifies packaged assets, and invokes the installed CLI.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> None:
    from fastapi.testclient import TestClient

    import mapf
    from mapf.analytics.diagnostics_report import generate_html_report
    from mapf.application.diagnostics import diagnose
    from mapf.gui.app import create_app

    module = Path(mapf.__file__).resolve()
    assert "site-packages" in module.parts, f"Editable/source import: {module}"
    doctor = diagnose(required=["gui", "analysis"])
    assert doctor["status"] == "ok", doctor
    assert doctor["package_version"] == mapf.__version__, doctor
    plan = subprocess.run(
        [sys.executable, "-m", "mapf.cli", "workspace-plan", "--profile", "smoke-v1"],
        capture_output=True,
        text=True,
        check=True,
    )
    planned = json.loads(plan.stdout)
    assert planned["count"] == 4
    with tempfile.TemporaryDirectory(prefix="decmapf-wheel-") as scratch:
        root = Path(scratch)
        with TestClient(create_app(root / "workspace")) as client:
            page = client.get("/")
            assert (
                page.status_code == 200 and "DEC-MAPF | MAPF simulation workspace" in page.text
            )
            assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page.text)
            assert assets and all(
                client.get(path).status_code == 200 for path in assets
            )
            notices = client.get("/THIRD_PARTY_NOTICES.txt")
            inventory = client.get("/license-inventory.json")
            assert notices.status_code == inventory.status_code == 200
            assert "Permission is hereby granted" in notices.text
            assert len(inventory.json()["components"]) == 19
            response = client.post(
                "/api/v1/jobs",
                json={
                    "scenario_id": "crossing-2a",
                    "solver_id": "Prioritized",
                    "setting": "SETTING_4",
                    "timeout_sec": 10,
                },
            )
            assert response.status_code == 202, response.text
            jid = response.json()["job_id"]
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                job = client.get("/api/v1/jobs/" + jid).json()
                if job["state"] not in ("pending", "running"):
                    break
                time.sleep(0.02)
            assert job["state"] == "completed", job
            assert job["result"]["validation"]["status"] == "valid_solution"
            rid = job["run_id"]
            installed_provenance = client.get(f"/api/v1/runs/{rid}").json()["metadata"]["provenance"]
            assert installed_provenance["git_commit"] == "unavailable"
            assert installed_provenance["working_tree_dirty"] is None
            assert installed_provenance["source_origin"] == "installed-package"
            bundle = client.get(f"/api/v1/runs/{rid}/export/json").json()
            assert client.post("/api/v1/runs/import", json=bundle).status_code == 201
            assert client.get(f"/api/v1/runs/{rid}/export/html").status_code == 200
        output = root / "diagnostics.html"
        with contextlib.redirect_stdout(io.StringIO()):
            generate_html_report(
                "wheel-smoke",
                {},
                {"density_matrix": [[0, 0], [0, 0]]},
                {},
                {},
                {},
                {},
                [],
                2,
                2,
                output,
            )
        assert output.is_file() and output.stat().st_size > 1000
        print(
            json.dumps(
                {
                    "status": "passed",
                    "doctor": doctor,
                    "module": str(module),
                    "python": sys.version,
                    "assets": assets,
                    "job_id": jid,
                    "run_id": rid,
                    "checks": [
                        "installed CLI",
                        "local packaged assets",
                        "packaged GUI license text and inventory",
                        "real spawned worker",
                        "independent validator",
                        "bundle import",
                        "offline export",
                        "packaged diagnostics renderer",
                    ],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
