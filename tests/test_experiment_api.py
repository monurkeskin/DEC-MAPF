"""Qualify the GUI experiment workflow against real, bounded local solver jobs."""

import hashlib
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from mapf.gui.app import create_app


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    directory = tmp_path_factory.mktemp("http-experiment")
    with TestClient(create_app(directory)) as client:
        spec = {
            "name": "HTTP acceptance fixtures",
            "scenarios": [
                {"scenario_id": "crossing-2a"},
                {"scenario_id": "grid-8x8-4a"},
            ],
            "defaults": {"setting": "SETTING_4", "timeout_sec": 10},
            "matrix": {"solver_id": ["CBS", "Prioritized"]},
            "budget": {
                "workers": 2,
                "wall_seconds": 30,
                "max_trials": 4,
                "disk_mb": 128,
            },
        }
        preview = client.post("/api/v1/experiments/preview", json=spec)
        assert preview.status_code == 200, preview.text
        manifest = preview.json()
        started = client.post("/api/v1/experiments", json={"manifest": manifest})
        assert started.status_code == 202, started.text
        url = f"/api/v1/experiments/{manifest['experiment_id']}"
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            state = client.get(url).json()
            if state["state"] == "completed":
                break
            time.sleep(0.05)
        else:
            pytest.fail(f"Bounded experiment did not complete: {state}")
        assert state["counts"] == {"completed": 4}
        yield client, url, manifest


def test_experiment_routes_preserve_manifest_and_all_trial_rows(experiment):
    client, url, manifest = experiment
    assert client.get(url + "/manifest").json() == manifest
    rows = client.get(url + "/rows").json()
    assert {row["trial_id"] for row in rows} == {
        trial["trial_id"] for trial in manifest["trials"]
    }
    assert all(row["validation_status"] == "valid_solution" for row in rows)
    summaries = client.get("/api/v1/experiments").json()
    assert any(row["experiment_id"] == manifest["experiment_id"] for row in summaries)
    assert client.get(url).json()["driver_error"] is None
    stopped = client.post(url + "/stop")
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "completed"
    assert client.get(url).json()["state"] == "completed"
    assert (
        client.post("/api/v1/experiments/experiment-unrelated/stop").status_code == 422
    )


def test_http_analysis_uses_independent_scenarios_and_retains_empty_filters(experiment):
    client, url, _ = experiment
    request = {"left": "CBS", "right": "Prioritized"}
    response = client.post(url + "/analysis", json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["coverage"]["both_solved"] == 2
    assert result["left"]["independent_units"] == 2
    assert result["left"]["interval"] == [1, 1]
    filtered = client.post(
        url + "/analysis", json={**request, "filters": {"random_seed": [99]}}
    ).json()
    assert filtered["left"]["planned"] == 0
    assert filtered["left"]["success_rate"] is None
    assert filtered["cost"]["interval"] is None
    assert (
        client.post(url + "/analysis", json={"left": "CBS", "right": "CBS"}).status_code
        == 422
    )


def test_analysis_export_is_consistent_with_its_cohort_and_file_receipts(experiment):
    client, url, manifest = experiment
    request = {"left": "CBS", "right": "Prioritized"}
    analysis = client.post(url + "/analysis", json=request).json()
    request["expected_cohort_sha256"] = analysis["cohort_sha256"]
    response = client.post(url + "/export", json=request)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert json.loads(archive.read("experiment-manifest.json")) == manifest
        assert json.loads(archive.read("analysis.json")) == analysis
        assert len(json.loads(archive.read("all-planned-trials.json"))) == 4
        receipt = json.loads(archive.read("manifest.json"))
        for name, checksum in receipt["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum
        assert archive.read("success.pdf").startswith(b"%PDF")
        assert archive.read("success.png").startswith(b"\x89PNG")
        assert "Scenario-weighted" in archive.read("success.svg").decode()
    request["expected_cohort_sha256"] = "outdated-cohort"
    rejected = client.post(url + "/export", json=request)
    assert rejected.status_code == 422
    assert "analyze again" in rejected.json()["detail"]


@pytest.mark.parametrize("suffix", ["", "/rows", "/manifest"])
def test_unknown_experiment_is_not_an_internal_server_error(experiment, suffix):
    client, _, _ = experiment
    response = client.get("/api/v1/experiments/experiment-missing" + suffix)
    assert response.status_code == 404, response.text
