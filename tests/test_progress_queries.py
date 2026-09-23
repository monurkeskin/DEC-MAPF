"""Fast progress keeps verified outcomes, missing artifacts and latest attempts visible."""

import shutil
from pathlib import Path

import pytest

from mapf.application.experiments import ExperimentService, compile_experiment
from mapf.application.runs import RunRepository, encode


@pytest.fixture(scope="module")
def completed_workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("completed-progress-workspace")
    service = ExperimentService(RunRepository(root))
    manifest = compile_experiment(
        {
            "name": "progress witness",
            "scenarios": [
                {"scenario_id": "crossing-2a", "solver_id": "CBS", "timeout_sec": 10}
            ],
            "budget": {
                "workers": 1,
                "wall_seconds": 20,
                "max_trials": 1,
                "disk_mb": 64,
            },
        }
    )
    assert service.execute(manifest)["successful"] == 1
    assert service.repository.active_jobs() == []
    return root, manifest["experiment_id"]


@pytest.fixture
def completed(tmp_path, completed_workspace):
    # Generate a real result once; each corruption test owns a separate journal
    # and artifact copy. No live SQLite connection or supervisor is shared.
    source, experiment_id = completed_workspace
    workspace = shutil.copytree(source, tmp_path / "workspace")
    return ExperimentService(RunRepository(workspace)), experiment_id


def test_repeated_progress_does_not_reread_unchanged_verified_artifact(
    completed, monkeypatch
):
    service, experiment_id = completed
    expected = service.summary(experiment_id)
    original = Path.read_bytes
    reads = []

    def counted(path):
        if path.parent == service.repository.artifacts:
            reads.append(path)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", counted)
    assert service.summary(experiment_id) == expected
    assert reads == []


def test_changed_artifact_is_reverified_and_corruption_is_not_hidden(completed):
    service, experiment_id = completed
    job = service.repository.list_jobs()[0]
    path = service.repository.artifacts / f"{job['run_id']}.json"
    with path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="integrity"):
        service.summary(experiment_id)


def test_deleted_artifact_remains_in_the_denominator(completed):
    service, experiment_id = completed
    job = service.repository.list_jobs()[0]
    (service.repository.artifacts / f"{job['run_id']}.json").unlink()
    summary = service.summary(experiment_id)
    assert summary["planned"] == 1 and summary["successful"] == 0
    assert summary["counts"] == {"artifact_missing": 1}


def test_compact_latest_attempt_does_not_drop_attempt_lineage(completed):
    service, experiment_id = completed
    first = service.repository.list_jobs()[0]
    retry = {
        **first,
        "job_id": "job-" + "f" * 32,
        "state": "failed",
        "attempt_index": 1,
        "created_at": first["created_at"] + 1,
        "error": "controlled infrastructure failure",
        "parent_job_id": first["job_id"],
    }
    with service.repository.connect() as db:
        db.execute(
            "INSERT INTO jobs VALUES(?,?,?,?,?)",
            (
                retry["job_id"],
                None,
                "test",
                encode(retry).decode(),
                retry["created_at"],
            ),
        )
    latest = service.store.latest_attempts(experiment_id)[first["trial_id"]]
    assert latest["attempt_count"] == 2 and latest["job_id"] == retry["job_id"]
    assert "result" not in latest and "effective_config" not in latest
    assert len(service.attempts(experiment_id)[first["trial_id"]]) == 2
    assert service.summary(experiment_id)["counts"] == {"failed": 1}
    assert service.summary(experiment_id)["successful"] == 0
