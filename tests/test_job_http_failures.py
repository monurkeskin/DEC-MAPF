"""HTTP cancellation must cover all active jobs, independent of list pagination."""

import pytest
from fastapi.testclient import TestClient

from mapf.application.resources import (
    MIB,
    ResourceAdmission,
    ResourcePolicy,
    ResourceSnapshot,
)
from mapf.application.runs import new_id
from mapf.gui.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as value:
        yield value


class BlockedProbe:
    def sample(self, processes):
        return ResourceSnapshot(64 * 1024 * MIB, 100)


def test_batch_cancel_includes_active_jobs_older_than_the_last_list_page(client):
    repo, supervisor = client.app.state.workspace_services()
    with supervisor._mutex:
        supervisor.admission = ResourceAdmission(ResourcePolicy(), BlockedProbe())
    request = {"jobs": [{"scenario_id": "crossing-2a", "solver_id": "CBS"}]}
    plan = client.post("/api/v1/plans/preview", json=request).json()
    response = client.post(
        "/api/v1/batches",
        json={**request, "plan_digest": plan["plan_digest"]},
        headers={"Idempotency-Key": "older-batch"},
    )
    assert response.status_code == 202
    batch = response.json()
    oldest = repo.get_job(batch["jobs"][0])
    for index in range(101):
        archived = {
            **oldest,
            "job_id": new_id("job"),
            "run_id": new_id("run"),
            "attempt_id": new_id("attempt"),
            "batch_id": None,
            "created_at": oldest["created_at"] + index + 1,
        }
        repo.admit(archived, None, f"fixture-{index}", max_pending=10)
        repo.transition(archived["job_id"], "failed", error="historical fixture")
    cancelled = client.post(f"/api/v1/batches/{batch['batch_id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled_attempts"] == 1
    assert repo.get_job(oldest["job_id"])["state"] == "cancelled"
    assert (
        client.post(f"/api/v1/batches/{batch['batch_id']}/cancel").json()[
            "cancelled_attempts"
        ]
        == 0
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/jobs/{job}"),
        ("POST", "/jobs/{job}/retry"),
        ("POST", "/jobs/{job}/cancel"),
        ("GET", "/jobs/{job}/events"),
        ("GET", "/jobs/{job}/stream"),
        ("GET", "/runs/{run}"),
        ("GET", "/runs/{run}/telemetry"),
        ("GET", "/runs/{run}/frames"),
        ("POST", "/runs/{run}/pin"),
        ("DELETE", "/runs/{run}"),
        ("GET", "/runs/{run}/export/json"),
    ],
    ids=[
        "job",
        "retry",
        "cancel",
        "events",
        "stream",
        "run",
        "telemetry",
        "frames",
        "pin",
        "delete",
        "export",
    ],
)
def test_absent_resources_return_not_found_without_admission(client, method, path):
    response = client.request(
        method, "/api/v1" + path.format(job=new_id("job"), run=new_id("run"))
    )
    assert response.status_code == 404
    assert client.get("/api/v1/jobs").json() == []
    assert client.get("/api/v1/runs").json() == []


def test_invalid_idempotency_key_is_not_misreported_as_a_conflict(client):
    response = client.post(
        "/api/v1/jobs",
        json={"scenario_id": "crossing-2a"},
        headers={"Idempotency-Key": " "},
    )
    assert response.status_code == 422
    assert client.get("/api/v1/jobs").json() == []
