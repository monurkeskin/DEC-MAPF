"""Tests for Gate G1 application services and API routes (GUI-008 through GUI-016)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from mapf.application.scenarios import ScenarioService
from mapf.application.solvers import SolverRegistry
from mapf.core.models import Point
from mapf.gui.app import create_app
from mapf.solvers.base import MAPFInstance


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        yield client


def test_solver_registry_capabilities():
    """Verify GUI-008 & GUI-009: solver registry lists all solvers and schemas correctly."""
    caps = SolverRegistry.list_capabilities()
    assert len(caps) >= 5
    solver_ids = {c.solver_id for c in caps}
    assert "Decentralized-HeatMap" in solver_ids
    assert "Decentralized-PathAware" in solver_ids
    assert "CBS" in solver_ids
    assert "EECBS-1.1" in solver_ids
    assert "Prioritized" in solver_ids

    hm = SolverRegistry.get_capability("Decentralized-HeatMap")
    assert hm is not None
    assert hm.supports_fov is True
    assert hm.supports_commitments is True
    assert hm.supports_tokens is True
    assert len(hm.parameters) >= 3


def test_scenario_service_validation():
    """Verify GUI-010: semantic validation flags obstacles and disconnections."""
    # Valid instance
    _, _, _, inst_valid, _ = ScenarioService.create_crossing_scenario()
    errs = ScenarioService.validate_instance(inst_valid)
    assert len(errs) == 0

    # Invalid instance: start on obstacle
    inst_invalid = MAPFInstance(
        grid_width=5,
        grid_height=5,
        obstacles={Point(x=1, y=1)},
        starts={"agent_0": Point(x=1, y=1)},
        goals={"agent_0": Point(x=4, y=4)},
    )
    errs = ScenarioService.validate_instance(inst_invalid)
    assert any("on obstacle" in e for e in errs)

    # Invalid instance: disconnected goal (surrounded by obstacles)
    wall = {Point(x=3, y=4), Point(x=4, y=3), Point(x=3, y=3)}
    inst_trapped = MAPFInstance(
        grid_width=5,
        grid_height=5,
        obstacles=wall,
        starts={"agent_0": Point(x=0, y=0)},
        goals={"agent_0": Point(x=4, y=4)},
    )
    errs = ScenarioService.validate_instance(inst_trapped)
    assert any("No valid path exists" in e for e in errs)


def test_api_capabilities_endpoint(client):
    """Verify GET /api/v1/capabilities."""
    resp = client.get("/api/v1/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 5
    assert any(c["solver_id"] == "Decentralized-HeatMap" for c in data)


def test_api_scenarios_endpoint(client):
    """Verify GET /api/v1/scenarios and GET /api/v1/scenarios/{id}."""

    resp = client.get("/api/v1/scenarios")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) >= 3
    s_id = scenarios[0]["scenario_id"]

    resp_det = client.get(f"/api/v1/scenarios/{s_id}")
    assert resp_det.status_code == 200
    det = resp_det.json()
    assert "instance_hash" in det
    assert "starts" in det
    assert "goals" in det


def test_api_job_lifecycle_and_persistence(client):
    """Verify GUI-011, GUI-012, GUI-013, GUI-014: Job submission, async execution, validation, and run persistence."""

    # Submit job using built-in crossing scenario
    req_data = {
        "solver_id": "Decentralized-HeatMap",
        "scenario_id": "crossing-2a",
        "max_steps": 50,
        "timeout_sec": 5.0,
        "fov_size": 3,
        "initial_tokens": 10,
        "commitment_type": "SC",
        "random_seed": 42,
    }
    resp_submit = client.post("/api/v1/jobs", json=req_data)
    assert resp_submit.status_code == 202
    res_json = resp_submit.json()
    job_id = res_json["job_id"]
    run_id = res_json["run_id"]
    assert job_id.startswith("job-")

    # Poll until complete
    timeout = 10.0
    start_t = time.time()
    job_data = None
    while time.time() - start_t < timeout:
        resp_status = client.get(f"/api/v1/jobs/{job_id}")
        assert resp_status.status_code == 200
        job_data = resp_status.json()
        if job_data["state"] in ("completed", "failed"):
            break
        time.sleep(0.1)

    assert job_data is not None
    assert job_data["state"] == "completed"
    assert job_data["result"] is not None
    assert job_data["result"]["success"] is True
    assert job_data["result"]["status"] == "solved"

    # Verify run repository has persisted this run
    resp_run = client.get(f"/api/v1/runs/{run_id}")
    assert resp_run.status_code == 200
    run_det = resp_run.json()
    assert run_det["metadata"]["run_id"] == run_id
    assert run_det["metadata"]["success"] is True
    assert len(run_det["frames"]) > 0

    # Verify listing runs
    resp_list = client.get("/api/v1/runs")
    assert resp_list.status_code == 200
    runs = resp_list.json()
    assert any(r["run_id"] == run_id for r in runs)


def test_api_scenario_validation_endpoint(client):
    """Verify POST /api/v1/scenarios/validate."""

    # Valid payload
    payload_valid = {
        "grid_width": 5,
        "grid_height": 5,
        "obstacles": [],
        "starts": {"agent_0": [0, 0], "agent_1": [4, 4]},
        "goals": {"agent_0": [4, 4], "agent_1": [0, 0]},
    }
    resp = client.post("/api/v1/scenarios/validate", json=payload_valid)
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True

    # Invalid payload: out of bounds
    payload_invalid = {
        "grid_width": 5,
        "grid_height": 5,
        "obstacles": [],
        "starts": {"agent_0": [10, 10]},
        "goals": {"agent_0": [4, 4]},
    }
    resp_bad = client.post("/api/v1/scenarios/validate", json=payload_invalid)
    assert resp_bad.status_code == 200
    assert resp_bad.json()["is_valid"] is False
    assert len(resp_bad.json()["errors"]) > 0


def test_api_job_sse_stream(client):
    """Verify GET /api/v1/jobs/{job_id}/stream (GUI-016)."""

    # Submit job
    req_data = {
        "solver_id": "Decentralized-HeatMap",
        "scenario_id": "crossing-2a",
        "max_steps": 20,
    }
    resp_submit = client.post("/api/v1/jobs", json=req_data)
    job_id = resp_submit.json()["job_id"]

    # Stream SSE
    with client.stream("GET", f"/api/v1/jobs/{job_id}/stream") as stream_resp:
        assert stream_resp.status_code == 200
        assert "text/event-stream" in stream_resp.headers["content-type"]
        lines = []
        for line in stream_resp.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 4:
                break
        assert any("event:" in l for l in lines)
