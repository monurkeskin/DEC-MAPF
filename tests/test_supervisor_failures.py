"""Owned-process failures cannot publish runs or leave a stopped owner locked."""

import json
import os
import time
from pathlib import Path

import pytest

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.jobs import JobSupervisor
from mapf.application.resources import MIB, ResourcePolicy, ResourceSnapshot
from mapf.application.runs import RunRepository


class BlockedProbe:
    def sample(self, processes):
        return ResourceSnapshot(64 * 1024 * MIB, 100)


def sleep_worker(job, output, connection):
    time.sleep(60)


def malformed_worker(job, output, connection):
    mode = job["effective_config"]["random_seed"]
    path = Path(output)
    if mode == 1:
        return  # No committed result.
    if mode == 2:
        path.write_text("not JSON")
    if mode == 3:
        path.write_text(json.dumps({"ok": False, "error": "worker rejected input"}))
    if mode == 4:
        with path.open("wb") as stream:
            stream.seek(50 * 1024 * 1024)
            stream.write(b"x")


def terminal(repo, job_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        state = repo.get_job(job_id)
        if state["state"] == "failed":
            return state
        time.sleep(0.03)
    pytest.fail(f"Job did not fail within the bounded check: {repo.get_job(job_id)['state']}")


def test_shutdown_journal_failure_releases_lease_after_owned_processes_stop(tmp_path, monkeypatch):
    repo = RunRepository(tmp_path)
    owner = JobSupervisor(repo, resource_policy=ResourcePolicy(), resource_probe=BlockedProbe())
    job = owner.submit(JobSubmissionRequest(scenario_id="crossing-2a"))
    def unavailable(*args, **kwargs):
        raise OSError("injected shutdown journal failure")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(repo, "transition", unavailable)
            with pytest.raises(OSError, match="shutdown journal"):
                owner.close()
        assert not owner._thread.is_alive()
        replacement = JobSupervisor(repo)
        try:
            assert repo.get_job(job["job_id"])["state"] == "interrupted"
        finally:
            replacement.close()
    finally:
        # Retain the failed owner above so garbage collection cannot hide a leak.
        owner._lease.close()


@pytest.mark.parametrize("phase", ["pending", "running"])
def test_monitor_failure_stops_owned_jobs_and_records_infrastructure_error(tmp_path, monkeypatch, phase):
    original = JobSupervisor._cycle
    def failed_cycle(self):
        if phase == "running":
            original(self)
        if self.repository.active_jobs():
            raise OSError("injected monitor failure")
    monkeypatch.setattr(JobSupervisor, "_cycle", failed_cycle)
    repo = RunRepository(tmp_path)
    owner = JobSupervisor(repo, worker=sleep_worker)
    try:
        job = owner.submit(JobSubmissionRequest(scenario_id="crossing-2a"))
        finished = terminal(repo, job["job_id"])
        assert "injected monitor failure" in finished["error"]
        assert "injected monitor failure" in owner.last_error
        assert repo.list_runs() == []
        if finished["worker_pid"] is not None:
            with pytest.raises(ProcessLookupError):
                os.kill(finished["worker_pid"], 0)
    finally:
        owner.close()


@pytest.mark.parametrize(("mode", "message"), [(1, "without a committed result"), (2, "JSONDecodeError"),
                                              (3, "worker rejected input"), (4, "exceeds the supported size")],
                         ids=["missing", "malformed", "worker-error", "oversized"])
def test_bad_staged_worker_result_is_failed_and_removed(tmp_path, mode, message):
    repo = RunRepository(tmp_path)
    owner = JobSupervisor(repo, worker=malformed_worker)
    try:
        job = owner.submit(JobSubmissionRequest(scenario_id="crossing-2a", random_seed=mode))
        finished = terminal(repo, job["job_id"])
        assert message in finished["error"]
        assert repo.list_runs() == []
        assert not list(repo.staging.glob("*.json"))
        assert repo.events(job["job_id"])[-1]["state"] == "failed"
    finally:
        owner.close()
