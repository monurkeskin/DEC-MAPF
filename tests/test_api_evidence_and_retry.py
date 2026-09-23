"""HTTP evidence exports and retry keep actual records and explicit attempt identity."""

import time
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from mapf.application.artifacts import export_bundle
from mapf.application.contracts import JobSubmissionRequest
from mapf.application.jobs import completed_payload
from mapf.application.plans import preview, provenance
from mapf.application.resources import ResourceAdmission, ResourcePolicy
from mapf.application.runs import new_id
from mapf.application.worker import solve_plan
from mapf.gui.app import create_app
from tests.test_job_http_failures import BlockedProbe


@pytest.fixture(scope="module")
def recorded_run():
    plan = preview(JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=5))
    plan["provenance"] = provenance()
    job = {"job_id": new_id("job"), "run_id": new_id("run"), "attempt_id": new_id("attempt"),
           "definition_digest": plan["definition_digest"], "plan": plan,
           "effective_config": plan["effective_config"], "created_at": time.time(), "started_at": time.time()}
    return completed_payload(job, solve_plan(plan))


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as value:
        _, supervisor = value.app.state.workspace_services()
        with supervisor._mutex:
            supervisor.admission = ResourceAdmission(ResourcePolicy(), BlockedProbe())
        yield value


def test_current_telemetry_exports_the_recorded_sequence(client, recorded_run):
    repo, _ = client.app.state.workspace_services()
    repo.save_run(recorded_run)
    events = recorded_run["result"]["telemetry_events"]
    assert events  # Qualify real event validation, not just the empty-list response.
    response = client.get(f"/api/v1/runs/{recorded_run['metadata']['run_id']}/telemetry")
    assert response.status_code == 200, response.text
    # The HTTP event schema supplies nullable identities for synchronous recordings.
    expected = [{"run_id": None, "attempt_id": None, **event} for event in events]
    assert response.json() == {"schema_version": "telemetry-2", "events": expected}


def test_legacy_telemetry_stays_archivable_but_is_not_promoted_to_current_schema(client, recorded_run):
    old = deepcopy(recorded_run)
    old["result"]["telemetry_events"][0].pop("schema_version")
    repo, _ = client.app.state.workspace_services()
    repo.save_run(old)
    url = f"/api/v1/runs/{old['metadata']['run_id']}"
    response = client.get(url + "/telemetry")
    assert response.status_code == 422
    assert "Legacy events" in response.json()["detail"]
    archived = client.get(url + "/export/json")
    assert archived.status_code == 200
    assert archived.json()["payload"]["result"]["telemetry_events"] == old["result"]["telemetry_events"]


def test_bad_export_and_malformed_import_do_not_change_stored_runs(client, recorded_run):
    repo, _ = client.app.state.workspace_services()
    repo.save_run(recorded_run)
    response = client.get(f"/api/v1/runs/{recorded_run['metadata']['run_id']}/export/unknown")
    assert response.status_code == 422
    before = repo.list_runs()
    response = client.post("/api/v1/runs/import", json=export_bundle({}))
    assert response.status_code == 422
    assert repo.list_runs() == before


def test_http_retry_requires_terminal_attempt_and_keeps_the_parent_identity(client):
    data = {"scenario_id": "crossing-2a", "solver_id": "CBS"}
    response = client.post("/api/v1/jobs", json=data, headers={"Idempotency-Key": "original"})
    assert response.status_code == 202
    original = response.json()
    url = f"/api/v1/jobs/{original['job_id']}"
    assert client.post(url + "/retry").status_code == 422
    assert client.post(url + "/cancel").json()["cancelled"] is True
    retried = client.post(url + "/retry")
    assert retried.status_code == 202, retried.text
    retry = retried.json()
    assert retry["job_id"] != original["job_id"]
    assert retry["attempt_id"] != original["attempt_id"]
    assert retry["definition_digest"] == original["definition_digest"]
    repo, _ = client.app.state.workspace_services()
    assert repo.get_job(retry["job_id"])["parent_job_id"] == original["job_id"]
    assert client.get(url).json()["state"] == "cancelled"


def test_same_idempotency_key_cannot_admit_different_inputs(client):
    data = {"scenario_id": "crossing-2a", "solver_id": "CBS"}
    headers = {"Idempotency-Key": "one-command"}
    first = client.post("/api/v1/jobs", json=data, headers=headers)
    repeated = client.post("/api/v1/jobs", json=data, headers=headers)
    assert first.json()["job_id"] == repeated.json()["job_id"]
    conflict = client.post("/api/v1/jobs", json={**data, "random_seed": 5}, headers=headers)
    assert conflict.status_code == 409
    assert len(client.get("/api/v1/jobs").json()) == 1


def test_batch_cancellation_leaves_other_pending_work_in_place(client):
    unrelated = client.post("/api/v1/jobs", json={"scenario_id": "crossing-2a"}).json()
    request = {"jobs": [{"scenario_id": "grid-8x8-4a", "solver_id": "CBS"}]}
    plan = client.post("/api/v1/plans/preview", json=request).json()
    batch = client.post("/api/v1/batches", json={**request, "plan_digest": plan["plan_digest"]},
                        headers={"Idempotency-Key": "one-batch"}).json()
    cancelled = client.post(f"/api/v1/batches/{batch['batch_id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled_attempts"] == 1
    assert client.get(f"/api/v1/jobs/{unrelated['job_id']}").json()["state"] == "pending"
