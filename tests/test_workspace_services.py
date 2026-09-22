"""Real application/worker regression cases, isolated from personal run data."""

from __future__ import annotations

import copy
import os
import time

import pytest
from fastapi.testclient import TestClient

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.jobs import JobSupervisor
from mapf.application.plans import preview
from mapf.application.runs import TERMINAL, RunRepository, digest
from mapf.application.worker import solve_plan
from mapf.gui.app import create_app


def uncooperative_worker(job, output, connection):
    time.sleep(60)


def crash_worker(job, output, connection):
    os._exit(19)


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        yield c


def submit(client, **overrides):
    return client.post(
        "/api/v1/jobs",
        json=dict(
            scenario_id="crossing-2a",
            solver_id="CBS",
            setting="SETTING_4",
            timeout_sec=10,
            **overrides,
        ),
    )


def wait(client, job_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = client.get(f"/api/v1/jobs/{job_id}").json()
        if result["state"] in TERMINAL:
            return result
        time.sleep(0.05)
    pytest.fail("real worker exceeded test deadline")


def test_real_worker_idempotency_setting_and_headless_parity(client):
    request = {
        "scenario_id": "grid-8x8-4a",
        "solver_id": "Prioritized",
        "setting": "SETTING_4",
        "timeout_sec": 10,
    }
    a = client.post("/api/v1/jobs", json=request, headers={"Idempotency-Key": "once"})
    b = client.post("/api/v1/jobs", json=request, headers={"Idempotency-Key": "once"})
    assert a.status_code == b.status_code == 202
    assert a.json()["job_id"] == b.json()["job_id"]
    conflict = client.post(
        "/api/v1/jobs",
        json=dict(request, random_seed=3),
        headers={"Idempotency-Key": "once"},
    )
    assert conflict.status_code == 409
    result = wait(client, a.json()["job_id"])
    assert result["state"] == "completed", result
    assert result["effective_config"]["setting"] == "SETTING_4"
    assert result["result"]["validation"]["status"] == "valid_solution"
    headless = solve_plan(preview(JobSubmissionRequest(**request)))["result"]
    for key in ("paths", "makespan", "sum_of_costs", "validation", "status"):
        assert result["result"][key] == headless[key]
    again = client.post("/api/v1/jobs", json=request).json()
    assert again["run_id"] != a.json()["run_id"]
    assert again["attempt_id"] != a.json()["attempt_id"]
    assert again["definition_digest"] == a.json()["definition_digest"]
    wait(client, again["job_id"])


@pytest.mark.parametrize(
    "patch",
    [
        {"solver_id": "made-up"},
        {"fov_size": 4},
        {"commitment_type": "SPATIAL"},
        {"starts": {"a": [1]}},
        {"starts": {"a": [True, 0]}},
        {"unexpected": True},
    ],
)
def test_malformed_submission_never_admitted(client, patch):
    result = client.post("/api/v1/jobs", json=dict(scenario_id="crossing-2a", **patch))
    assert result.status_code == 422
    assert client.get("/api/v1/jobs").json() == []


def test_cursor_multiobserver_reconnect_and_restart(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        admission = submit(c).json()
        job_id = admission["job_id"]
        assert wait(c, job_id)["state"] == "completed"
        first = c.get(f"/api/v1/jobs/{job_id}/stream").text
        second = c.get(f"/api/v1/jobs/{job_id}/stream").text
        assert first == second
        assert first.count("event: done") == 1
        resumed = c.get(
            f"/api/v1/jobs/{job_id}/stream", headers={"Last-Event-ID": "1"}
        ).text
        assert "id: 1\n" not in resumed and "id: 2\n" in resumed
        assert c.get(f"/api/v1/jobs/{job_id}/stream?cursor=999").status_code == 409
        assert (
            c.get(
                f"/api/v1/jobs/{job_id}/stream", headers={"Last-Event-ID": "oops"}
            ).status_code
            == 422
        )
    with TestClient(create_app(tmp_path)) as c:
        assert c.get(f"/api/v1/jobs/{job_id}").json()["state"] == "completed"
        assert c.get(f"/api/v1/jobs/{job_id}/stream").text == first
        run = c.get(f"/api/v1/runs/{admission['run_id']}").json()
        assert run["frames"][0]["positions"] == {"agent_0": [0, 2], "agent_1": [2, 0]}


def test_running_and_queued_cancel_stop_owned_process(tmp_path):
    repo = RunRepository(tmp_path)
    manager = JobSupervisor(repo, max_workers=1, worker=uncooperative_worker)
    try:
        req = JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=20)
        a, b = manager.submit(req), manager.submit(req)
        deadline = time.monotonic() + 5
        while (
            repo.get_job(a["job_id"])["state"] != "running"
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        pid = repo.get_job(a["job_id"])["worker_pid"]
        assert pid is not None
        assert manager.cancel_job(b["job_id"])
        start = time.monotonic()
        assert manager.cancel_job(a["job_id"])
        assert time.monotonic() - start < 2
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        assert not manager.cancel_job(a["job_id"])
        assert repo.get_job(a["job_id"])["state"] == "cancelled"
        assert repo.get_job(b["job_id"])["state"] == "cancelled"
        assert repo.list_runs() == []
        assert len([e for e in repo.events(a["job_id"]) if e["type"] == "done"]) == 1
    finally:
        manager.close()


@pytest.mark.parametrize(
    "worker, expected, budget",
    [(uncooperative_worker, "timed_out", 0.8), (crash_worker, "failed", 10.0)],
)
def test_worker_failure_and_wall_clock_budget(tmp_path, worker, expected, budget):
    # A timeout includes cold spawn/imports. Give the crash witness enough time
    # to reach its injected os._exit even while independent browser/build work runs.
    # The separate timeout witness retains its deliberately short 0.8 s deadline.
    repo = RunRepository(tmp_path)
    manager = JobSupervisor(repo, max_workers=1, worker=worker)
    try:
        j = manager.submit(
            JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=budget)
        )
        deadline = time.monotonic() + budget + 5
        while (
            repo.get_job(j["job_id"])["state"] not in TERMINAL
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert repo.get_job(j["job_id"])["state"] == expected
        assert repo.list_runs() == []
    finally:
        manager.close()


def test_bundle_roundtrip_tampering_and_safe_exports(client):
    job = wait(client, submit(client).json()["job_id"])
    rid = job["run_id"]
    bundle = client.get(f"/api/v1/runs/{rid}/export/json").json()
    assert bundle["sha256"] == digest(bundle["payload"])
    original = copy.deepcopy(bundle)
    imported = client.post("/api/v1/runs/import", json=bundle)
    assert imported.status_code == 201, imported.text
    assert imported.json()["run_id"] != rid
    saved = client.get("/api/v1/runs/" + imported.json()["run_id"]).json()
    assert saved["result"]["paths"] == job["result"]["paths"]
    bundle["payload"]["metadata"]["success"] = False
    assert client.post("/api/v1/runs/import", json=bundle).status_code == 422
    original["payload"]["result"]["paths"]["agent_0"][0]["x"] = 4
    original["sha256"] = digest(original["payload"])
    assert client.post("/api/v1/runs/import", json=original).status_code == 422
    for kind, marker in [
        ("svg", "<svg"),
        ("csv", "sum_of_costs"),
        ("tex", "begin{tabular}"),
        ("html", "offline replay"),
    ]:
        result = client.get(f"/api/v1/runs/{rid}/export/{kind}")
        assert result.status_code == 200 and marker in result.text
    assert client.get(f"/api/v1/runs/{rid}/export/svg?tick=999").status_code == 422
    assert (
        client.get(f"/api/v1/runs/{rid}/frames?offset=1&limit=2").json()["frames"][0][
            "tick"
        ]
        == 1
    )


def test_quota_failure_pin_and_artifact_corruption(client):
    j = wait(client, submit(client).json()["job_id"])
    rid = j["run_id"]
    assert client.post(f"/api/v1/runs/{rid}/pin").status_code == 200
    assert client.delete(f"/api/v1/runs/{rid}").status_code == 422
    repo, _ = client.app.state.workspace_services()
    path = repo.artifacts / f"{rid}.json"
    original = path.read_bytes()
    path.write_bytes(b"{}")
    assert client.get(f"/api/v1/runs/{rid}").status_code == 422
    path.write_bytes(original)
    repo.quota_bytes = 1
    assert submit(client).status_code == 507
    assert client.post(f"/api/v1/runs/{rid}/pin?pinned=false").status_code == 200
    assert client.delete(f"/api/v1/runs/{rid}").status_code == 200


def test_recovery_marks_interrupted_and_ignores_late_completion(tmp_path):
    repo = RunRepository(tmp_path)
    manager = JobSupervisor(repo, worker=uncooperative_worker)
    j = manager.submit(JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=20))
    manager.close()
    assert repo.get_job(j["job_id"])["state"] == "interrupted"
    repo.transition(j["job_id"], "completed")
    assert repo.get_job(j["job_id"])["state"] == "interrupted"
    with pytest.raises(ValueError):
        repo.get_run("../../secret")


def test_comparison_matches_units_and_preserves_denominators(client):
    a = wait(client, submit(client).json()["job_id"])
    payload = {
        "scenario_id": "crossing-2a",
        "solver_id": "Prioritized",
        "setting": "SETTING_4",
        "timeout_sec": 10,
    }
    b = wait(client, client.post("/api/v1/jobs", json=payload).json()["job_id"])
    request = {
        "left": [a["run_id"]],
        "right": [b["run_id"]],
        "treatment_keys": ["solver_id"],
    }
    result = client.post("/api/v1/comparisons", json=request).json()
    assert result["paired"] == 1 and result["common_solved"] == 1
    assert (
        result["rows"][0]["deltas_right_minus_left"]["makespan"]
        == b["result"]["makespan"] - a["result"]["makespan"]
    )
    duplicate = client.post(
        "/api/v1/comparisons", json=dict(request, left=[a["run_id"], a["run_id"]])
    )
    assert duplicate.status_code == 422
    changed = wait(
        client,
        client.post("/api/v1/jobs", json=dict(payload, random_seed=7)).json()["job_id"],
    )
    assert (
        client.post(
            "/api/v1/comparisons", json=dict(request, right=[changed["run_id"]])
        ).json()["paired"]
        == 0
    )
    assert (
        client.post(
            "/api/v1/comparisons", json=dict(request, treatment_keys=["random_seed"])
        ).status_code
        == 422
    )
    assert result["paired_coverage"] == {
        "both_solved": 1,
        "left_only": 0,
        "right_only": 0,
        "neither_solved": 0,
    }


def test_batch_preview_admission_is_atomic_and_idempotent(client):
    requests = [
        {
            "scenario_id": "crossing-2a",
            "solver_id": "Prioritized",
            "setting": "SETTING_4",
            "timeout_sec": 10,
        }
    ] * 2
    plan = client.post("/api/v1/plans/preview", json={"jobs": requests}).json()
    body = {"jobs": requests, "plan_digest": plan["plan_digest"]}
    a = client.post(
        "/api/v1/batches", json=body, headers={"Idempotency-Key": "batch-once"}
    )
    b = client.post(
        "/api/v1/batches", json=body, headers={"Idempotency-Key": "batch-once"}
    )
    assert a.status_code == b.status_code == 202
    assert a.json() == b.json()
    altered = [dict(requests[0], random_seed=13)]
    new_plan = client.post("/api/v1/plans/preview", json={"jobs": altered}).json()
    assert (
        client.post(
            "/api/v1/batches",
            json={"jobs": altered, "plan_digest": new_plan["plan_digest"]},
            headers={"Idempotency-Key": "batch-once"},
        ).status_code
        == 409
    )
    assert len(client.get("/api/v1/jobs").json()) == 2
    for job_id in a.json()["jobs"]:
        wait(client, job_id)


def test_disk_failure_does_not_publish_run(client, monkeypatch):
    import mapf.application.runs as storage

    def fail(*args, **kwargs):
        raise OSError("synthetic disk-full injection")

    monkeypatch.setattr(storage, "atomic_write", fail)
    response = submit(client)
    state = wait(client, response.json()["job_id"])
    assert state["state"] == "failed"
    assert "disk-full" in state["error"]
    assert client.get("/api/v1/runs").json() == []


def test_movingai_import_and_legacy_quarantine(client):
    data = {
        "map_text": "type octile\nheight 3\nwidth 3\nmap\n...\n.@.\n...\n",
        "scenario_text": "version 1\n0 tiny.map 3 3 0 0 2 2 4\n",
        "agent_count": 1,
        "setting": "SETTING_4",
    }
    response = client.post("/api/v1/scenarios/import-movingai", json=data)
    assert response.status_code == 201, response.text
    snap = response.json()
    assert snap["obstacles"] == [[1, 1]]
    loaded = client.get("/api/v1/scenarios/" + snap["scenario_id"]).json()
    assert loaded["source"]["map_sha256"] == snap["source"]["map_sha256"]
    assert (
        client.post(
            "/api/v1/scenarios/import-movingai",
            json=dict(data, map_text=data["map_text"].replace("width 3", "width 4")),
        ).status_code
        == 422
    )
    legacy = client.post(
        "/api/v1/archives/quarantine",
        json={"name": "legacy.csv", "content": "success,score\ntrue,3\n"},
    ).json()
    assert legacy["status"] == "quarantined"
    assert client.get("/api/v1/runs").json() == []


def test_readers_never_discover_orphan_artifact(tmp_path):
    from mapf.application.runs import new_id

    repo = RunRepository(tmp_path)
    name = new_id("run")
    (repo.artifacts / f"{name}.json").write_text("{}")
    assert repo.get_run(name) is None
    assert repo.recover() == 0
    assert not (repo.artifacts / f"{name}.json").exists()
    assert (repo.staging / f"orphan-{name}.json").exists()


def test_second_supervisor_cannot_take_over_live_work(tmp_path):
    repo = RunRepository(tmp_path)
    manager = JobSupervisor(repo)
    try:
        with pytest.raises(RuntimeError, match="already owns"):
            JobSupervisor(RunRepository(tmp_path))
    finally:
        manager.close()


def blocked_owned_worker(job, output, connection):
    # Exercise the real parent-death watchdog without doing scientific compute.
    from mapf.application import worker

    worker.solve_plan = lambda plan: time.sleep(60)
    worker.owned_worker(job, output, connection)


def supervisor_that_can_crash(directory):
    import json
    from pathlib import Path

    repo = RunRepository(directory)
    manager = JobSupervisor(repo, worker=blocked_owned_worker)
    j = manager.submit(JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=20))
    while repo.get_job(j["job_id"])["state"] != "running":
        time.sleep(0.02)
    Path(directory, "owned-process.json").write_text(
        json.dumps(repo.get_job(j["job_id"]))
    )
    time.sleep(60)


def test_supervisor_sigkill_stops_child_and_recovers_attempt(tmp_path):
    import json
    import multiprocessing
    import subprocess

    proc = multiprocessing.get_context("spawn").Process(
        target=supervisor_that_can_crash, args=(str(tmp_path),)
    )
    proc.start()
    try:
        ready = tmp_path / "owned-process.json"
        deadline = time.monotonic() + 6
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.03)
        assert ready.exists()
        data = json.loads(ready.read_text())
        pid = data["worker_pid"]
        proc.kill()
        proc.join(timeout=2)
        deadline = time.monotonic() + 4
        # Zombies have stopped executing and may briefly await the OS reaper.
        alive = True
        while time.monotonic() < deadline:
            status = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=False,
            )
            alive = (
                status.returncode == 0
                and status.stdout.strip()
                and not status.stdout.strip().startswith("Z")
            )
            if not alive:
                break
            time.sleep(0.05)
        assert not alive, "owned child survived supervisor death"
        repo = RunRepository(tmp_path)
        recovered = JobSupervisor(repo)
        try:
            assert repo.get_job(data["job_id"])["state"] == "interrupted"
            assert repo.list_runs() == []
        finally:
            recovered.close()
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)
        proc.close()
