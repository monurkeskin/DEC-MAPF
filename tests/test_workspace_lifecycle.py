"""Workspace inspection never creates a study or acquires somebody else's owner."""
import json
import sqlite3
import subprocess
import sys

import pytest

from mapf.application.experiments import ExperimentService, compile_experiment
from mapf.application.jobs import JobSupervisor
from mapf.application.resources import ResourcePolicy
from mapf.application.runs import RunRepository


def manifest(*, resources=False):
    budget = {"workers": 1, "wall_seconds": 10, "max_trials": 1, "disk_mb": 64}
    if resources:
        budget["resources"] = ResourcePolicy().model_dump()
    return compile_experiment({"name": "startup failure witness", "scenarios": [
        {"scenario_id": "crossing-2a", "solver_id": "CBS", "timeout_sec": 10}], "budget": budget})


def test_busy_owner_does_not_enroll_a_never_started_experiment(tmp_path):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    planned = manifest()
    owner = JobSupervisor(repository, max_workers=1)
    try:
        with pytest.raises(RuntimeError, match="already owns"):
            service.execute(planned)
        assert service.manifests() == []
        assert repository.list_jobs() == []
        assert owner._thread.is_alive()
    finally:
        owner.close()


def test_missing_optional_resource_probe_does_not_enroll(tmp_path, monkeypatch):
    service = ExperimentService(RunRepository(tmp_path))
    planned = manifest(resources=True)

    def unavailable(*args):
        raise ValueError("Install the resources extra")

    monkeypatch.setattr("mapf.application.jobs.ResourceAdmission", unavailable)
    with pytest.raises(ValueError, match="resources extra"):
        service.execute(planned)
    assert service.manifests() == []


def test_status_of_missing_workspace_fails_without_creating_it(tmp_path):
    workspace = tmp_path / "typo"
    result = subprocess.run([sys.executable, "-m", "mapf.cli", "batch", "status", "--workspace", str(workspace)],
                            text=True, capture_output=True, timeout=20, check=False)
    assert result.returncode == 1, result.stdout
    assert "does not exist" in json.loads(result.stdout)["error"]
    assert not workspace.exists()


def test_read_only_open_supports_legacy_empty_workspace_without_schema_changes(tmp_path):
    repository = RunRepository(tmp_path)
    with repository.connect() as database:
        database.execute("PRAGMA user_version=0")
    opened = RunRepository.open_existing(tmp_path)
    assert ExperimentService(opened).manifests() == []
    with opened.connect() as database:
        assert database.execute("PRAGMA user_version").fetchone()[0] == 0
        assert not database.execute("SELECT 1 FROM sqlite_master WHERE name='experiments'").fetchone()
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            database.execute("DELETE FROM jobs")


def test_future_workspace_schema_is_rejected_before_mutation(tmp_path):
    repository = RunRepository(tmp_path)
    with repository.connect() as database:
        database.execute("PRAGMA user_version=999")
    before = repository.db_path.read_bytes()
    with pytest.raises(ValueError, match="Unsupported workspace schema"):
        RunRepository(tmp_path)
    assert repository.db_path.read_bytes() == before


def test_failed_recovery_releases_its_own_lease(tmp_path, monkeypatch):
    repository = RunRepository(tmp_path)
    recover = repository.recover

    def unavailable():
        raise OSError("Cannot read recovery journal")

    monkeypatch.setattr(repository, "recover", unavailable)
    with pytest.raises(OSError, match="recovery journal"):
        JobSupervisor(repository)
    monkeypatch.setattr(repository, "recover", recover)
    owner = JobSupervisor(repository)
    owner.close()
