import json
import subprocess
import sys

from fastapi.testclient import TestClient

from mapf.application.profiles import preview_profile
from mapf.gui.app import create_app


def test_cli_gui_profile_manifest_identity(tmp_path):
    expected = preview_profile("smoke-v1")
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/v1/profiles/smoke-v1").json() == expected
        assert (
            client.get("/api/v1/profiles/historical-jaamas-subsample").status_code
            == 422
        )
    process = subprocess.run(
        [sys.executable, "-m", "mapf.cli", "workspace-plan", "--profile", "smoke-v1"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(process.stdout) == expected
    assert expected["count"] == 4 and expected["maximum_process_seconds"] == 40


def test_trace_levels_preserve_small_deterministic_scientific_outputs():
    from mapf.application.contracts import JobSubmissionRequest
    from mapf.application.plans import preview
    from mapf.application.worker import solve_plan

    # Eight declared strategy/setting cases, each under all three recording levels.
    for solver in ("Decentralized-HeatMap", "Decentralized-PathAware"):
        for setting in ("SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4"):
            results = []
            for level in ("metrics-only", "events", "full-trace"):
                request = JobSubmissionRequest(
                    scenario_id="crossing-2a",
                    solver_id=solver,
                    setting=setting,
                    recording_level=level,
                    max_steps=30,
                    timeout_sec=5,
                )
                results.append(solve_plan(preview(request))["result"])
            for key in (
                "paths",
                "makespan",
                "sum_of_costs",
                "validation",
                "status",
                "negotiation_count",
            ):
                assert results[0][key] == results[1][key] == results[2][key], (
                    solver,
                    setting,
                    key,
                )


def test_recorded_plans_are_actual_post_move_snapshots():
    from mapf.application.contracts import JobSubmissionRequest
    from mapf.application.plans import preview
    from mapf.application.worker import solve_plan

    request = JobSubmissionRequest(
        grid_width=4,
        grid_height=1,
        starts={"a": (0, 0)},
        goals={"a": (3, 0)},
        setting="SETTING_4",
        max_steps=5,
        recording_level="full-trace",
    )
    result = solve_plan(preview(request))["result"]
    assert result["frames"][0]["planned_paths"]["a"] == [[0, 0], [1, 0], [2, 0], [3, 0]]
    assert result["frames"][0]["local_observations"]["a"]["tick"] == 0
    assert result["frames"][1]["planned_paths"]["a"] == [[1, 0], [2, 0], [3, 0]]
    assert result["frames"][2]["planned_paths"]["a"] == [[2, 0], [3, 0]]
    assert result["frames"][1]["commitments"] == {"a": []}
    quiet = solve_plan(
        preview(request.model_copy(update={"recording_level": "metrics-only"}))
    )["result"]
    assert quiet["paths"] == result["paths"]
    assert all(not f["planned_paths"] for f in quiet["frames"])
