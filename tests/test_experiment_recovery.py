"""Failed trials stay visible and retries remain explicit and bounded."""

import threading

import pytest

from mapf.application.experiments import ExperimentService, compile_experiment
from mapf.application.jobs import JobSupervisor
from mapf.application.runs import RunRepository
from tests.worker_fixtures import failed_worker, stale_source_worker


def planned():
    # Failure/retry semantics need startup headroom, not a short timeout race.
    return compile_experiment(
        {
            "name": "failure lineage fixture",
            "scenarios": [
                {"scenario_id": "crossing-2a", "solver_id": "CBS", "timeout_sec": 30}
            ],
            "budget": {
                "workers": 1,
                "wall_seconds": 60,
                "max_trials": 1,
                "disk_mb": 64,
            },
        }
    )


def test_retry_failed_creates_one_attempt_per_invocation_and_preserves_parent(tmp_path):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    owner = JobSupervisor(repository, max_workers=1, worker=failed_worker)
    manifest = planned()
    eid = manifest["experiment_id"]
    try:
        assert service.execute(manifest, supervisor=owner)["counts"] == {"failed": 1}
        first = service.rows(eid)[0]
        unchanged = service.execute(manifest, resume=True, supervisor=owner)
        assert unchanged["planned"] == 1
        assert service.rows(eid)[0]["attempt_count"] == 1
        retried = service.execute(
            manifest, resume=True, retry_failed=True, supervisor=owner
        )
        assert retried["counts"] == {"failed": 1}
        assert retried["success_rate"] == 0
        history = service.attempts(eid)[first["trial_id"]]
        assert len(history) == 2
        assert history[-1]["parent_job_id"] == first["job_id"]
        assert service.rows(eid)[0]["attempt_count"] == 2
    finally:
        owner.close()


def test_source_mismatch_failure_stops_admission_and_is_not_silently_retried(tmp_path):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    owner = JobSupervisor(repository, max_workers=1, worker=stale_source_worker)
    manifest = planned()
    try:
        with pytest.raises(ValueError, match="Source changed during execution"):
            service.execute(manifest, supervisor=owner)
        assert service.summary(manifest["experiment_id"])["state"] == "failed"
        assert len(repository.list_jobs()) == 1
        assert repository.active_jobs() == []
    finally:
        owner.close()


def test_unhealthy_shared_owner_records_failed_experiment_without_admitting(tmp_path):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    owner = JobSupervisor(repository, max_workers=1)
    owner.last_error = "journal unavailable"
    manifest = planned()
    try:
        with pytest.raises(RuntimeError, match="journal unavailable"):
            service.execute(manifest, supervisor=owner)
        summary = service.summary(manifest["experiment_id"])
        assert summary["state"] == "failed"
        assert summary["counts"] == {"not_admitted": 1}
        assert repository.list_jobs() == []
    finally:
        owner.close()


def test_cleanup_error_cannot_leave_a_planned_or_running_experiment(
    tmp_path, monkeypatch
):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    manifest = planned()
    original = JobSupervisor.close

    def failed_close(owner):
        original(owner)
        raise OSError("injected shutdown journal failure")

    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(JobSupervisor, "close", failed_close)
    with pytest.raises(OSError, match="shutdown journal"):
        service.execute(manifest, stop=stop)
    assert service.summary(manifest["experiment_id"])["state"] == "failed"
    assert repository.active_jobs() == []


@pytest.mark.parametrize("deletion", ["retention", "missing-file"])
def test_deleted_result_stays_in_both_summary_and_export_population(tmp_path, deletion):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    manifest = planned()
    eid = manifest["experiment_id"]
    assert service.execute(manifest)["successful"] == 1
    first = service.rows(eid)[0]
    if deletion == "retention":
        repository.delete_run(first["run_id"])
    else:
        (repository.artifacts / f"{first['run_id']}.json").unlink()
    row = service.rows(eid)[0]
    assert row["state"] == "artifact_missing"
    assert row["sum_of_costs"] is None
    assert not row["success"]
    assert row["trial_id"] == first["trial_id"]
    assert service.summary(eid)["counts"] == {"artifact_missing": 1}
    assert service.summary(eid)["success_rate"] == 0
