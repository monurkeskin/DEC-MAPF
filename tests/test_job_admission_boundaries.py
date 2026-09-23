"""Admission and retry failures preserve the existing attempt ledger."""

import pytest

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.jobs import JobSupervisor
from mapf.application.plans import preview, preview_batch
from mapf.application.resources import ResourcePolicy
from mapf.application.runs import RunRepository
from tests.test_supervisor_failures import BlockedProbe


@pytest.fixture
def owner(tmp_path):
    value = JobSupervisor(RunRepository(tmp_path), resource_policy=ResourcePolicy(), resource_probe=BlockedProbe())
    try:
        yield value
    finally:
        value.close()


@pytest.mark.parametrize("admission", ["single", "batch", "frozen"])
def test_shutdown_rejects_every_admission_path_without_adding_a_job(owner, admission):
    request = JobSubmissionRequest(scenario_id="crossing-2a")
    plan = preview(request, owner.repository)
    batch = preview_batch([request], owner.repository)
    owner._stop.set()
    commands = {
        "single": lambda: owner.submit(request),
        "batch": lambda: owner.submit_batch([request], "batch", batch["plan_digest"]),
        "frozen": lambda: owner.submit_plan(plan, "plan"),
    }
    with pytest.raises(RuntimeError, match="shutting down"):
        commands[admission]()
    assert owner.repository.list_jobs() == []


@pytest.mark.parametrize(("key", "stale", "message"), [
    (" ", False, "Idempotency-Key"), ("k" * 129, False, "Idempotency-Key"),
    ("valid", True, "Plan changed"),
], ids=["blank", "oversized", "stale-preview"])
def test_batch_rejects_bad_command_identity_before_admission(owner, key, stale, message):
    request = JobSubmissionRequest(scenario_id="crossing-2a")
    digest = preview_batch([request], owner.repository)["plan_digest"]
    with pytest.raises(ValueError, match=message):
        owner.submit_batch([request], key, "stale" if stale else digest)
    assert owner.repository.list_jobs() == []


def test_retry_rejects_a_different_source_without_overwriting_the_terminal_attempt(owner, monkeypatch):
    job = owner.submit(JobSubmissionRequest(scenario_id="crossing-2a"))
    owner.cancel_job(job["job_id"])
    before = owner.repository.get_job(job["job_id"])
    monkeypatch.setattr("mapf.application.jobs.provenance", lambda: {"source_sha256": "different-source"})
    with pytest.raises(ValueError, match="original source"):
        owner.retry(job["job_id"])
    assert owner.repository.get_job(job["job_id"]) == before
    assert len(owner.repository.list_jobs()) == 1
