"""Experiment planning and interruption preserve the declared trial population."""

import threading
from copy import deepcopy

import pytest

from mapf.application.experiments import (
    ExperimentCoordinator,
    ExperimentService,
    compile_experiment,
    verify_manifest,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.runs import RunRepository, digest


def specification(**changes):
    return {
        "name": "experiment boundary fixture",
        "scenarios": [{"scenario_id": "crossing-2a", "solver_id": "CBS", "timeout_sec": 10}],
        "budget": {"workers": 1, "wall_seconds": 20, "max_trials": 2, "disk_mb": 64},
        **changes,
    }


@pytest.mark.parametrize(("changes", "message"), [
    ({"matrix": {"unknown": [1]}}, "Unknown matrix"),
    ({"exclude": [{"unknown": 1}]}, "Unknown matrix"),
    ({"matrix": {"random_seed": []}}, "at least one value"),
    ({"matrix": {"random_seed": [1, 2, 3]}}, "max_trials"),
    ({"exclude": [{"solver_id": "CBS"}]}, "All experiment trials"),
])
def test_invalid_expansion_is_rejected_before_registration(tmp_path, changes, message):
    repository = RunRepository(tmp_path)
    with pytest.raises(ValueError, match=message):
        compile_experiment(specification(**changes), repository)
    assert repository.list_jobs() == []


def test_expansion_limit_is_checked_before_exclusions():
    raw = specification(matrix={"random_seed": [1, 2, 3]}, exclude=[{"random_seed": 3}])
    with pytest.raises(ValueError, match="before exclusions"):
        compile_experiment(raw)


def test_manifest_identity_and_source_are_independent_guards():
    manifest = compile_experiment(specification())
    with pytest.raises(ValueError, match="identity"):
        verify_manifest({**manifest, "experiment_id": "experiment-wrong"})
    body = {key: value for key, value in manifest.items() if key not in {"manifest_digest", "experiment_id"}}
    body["source_sha256"] = "stale-source"
    checksum = digest(body)
    frozen = {**body, "manifest_digest": checksum, "experiment_id": "experiment-" + checksum[:24]}
    with pytest.raises(ValueError, match="Source changed"):
        verify_manifest(frozen)
    verify_manifest(frozen, check_source=False)


def test_sampling_units_and_override_order_survive_expansion():
    raw = specification(preset_id="interactive-v1", defaults={"random_seed": 3},
                        scenarios=[{"scenario_id": "crossing-2a", "random_seed": 4, "sampling_unit": "map-1"}],
                        matrix={"random_seed": [5, 6]})
    before = deepcopy(raw)
    manifest = compile_experiment(raw)
    assert [trial["plan"]["effective_config"]["random_seed"] for trial in manifest["trials"]] == [5, 6]
    assert {trial["sampling_unit"] for trial in manifest["trials"]} == {"map-1"}
    assert raw == before


def test_preexisting_stop_preserves_not_admitted_trials_and_releases_owner(tmp_path):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    stop = threading.Event()
    stop.set()
    manifest = compile_experiment(specification())
    summary = service.execute(manifest, stop=stop)
    assert summary["state"] == "interrupted"
    assert summary["counts"] == {"not_admitted": 1}
    assert repository.list_jobs() == []
    replacement = JobSupervisor(repository)
    replacement.close()


def test_registration_failure_releases_new_owner(tmp_path, monkeypatch):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)

    def failed_register(*args, **kwargs):
        raise OSError("registration disk failure")

    monkeypatch.setattr(service.store, "register", failed_register)
    with pytest.raises(OSError, match="registration disk"):
        service.execute(compile_experiment(specification()))
    replacement = JobSupervisor(repository)
    replacement.close()
    assert service.manifests() == []


@pytest.mark.parametrize("limit", ["elapsed", "disk"])
def test_exhausted_budget_never_admits_remaining_trials(tmp_path, monkeypatch, limit):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    manifest = compile_experiment(specification())
    service.register(manifest)
    if limit == "elapsed":
        service.store.update(manifest["experiment_id"], "interrupted", 21)
    else:
        monkeypatch.setattr(repository, "usage_bytes", lambda: 64 * 1024 * 1024)
    summary = service.execute(manifest, resume=True)
    assert summary["state"] == "budget_exhausted"
    assert summary["planned"] == 1
    assert summary["counts"] == {"not_admitted": 1}
    assert repository.list_jobs() == []


@pytest.mark.parametrize(("exception", "status"), [(KeyboardInterrupt, "interrupted"), (OSError, "failed")])
def test_execution_exception_retains_durable_status_and_releases_owner(tmp_path, monkeypatch, exception, status):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    manifest = compile_experiment(specification())

    def failure():
        raise exception("injected disk inspection failure")

    monkeypatch.setattr(repository, "usage_bytes", failure)
    if exception is KeyboardInterrupt:
        assert service.execute(manifest)["state"] == status
    else:
        with pytest.raises(OSError, match="injected disk"):
            service.execute(manifest)
    assert service.summary(manifest["experiment_id"])["state"] == status
    assert repository.active_jobs() == []
    replacement = JobSupervisor(repository)
    replacement.close()


@pytest.mark.parametrize("limit", ["workers", "disk"])
def test_gui_driver_checks_workspace_capacity_before_registering(tmp_path, limit):
    repository = RunRepository(tmp_path, quota_bytes=64 * 1024 * 1024)
    service = ExperimentService(repository)
    supervisor = JobSupervisor(repository, max_workers=1)
    driver = ExperimentCoordinator(service, supervisor)
    raw = specification()
    raw["budget"][limit if limit == "workers" else "disk_mb"] = 2 if limit == "workers" else 128
    try:
        with pytest.raises(ValueError, match="worker limit|disk budget"):
            driver.start(compile_experiment(raw))
        assert service.manifests() == []
        assert driver.active is None
    finally:
        driver.close()
        supervisor.close()


def test_gui_driver_surfaces_background_failure_and_stores_failed_status(tmp_path, monkeypatch):
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    supervisor = JobSupervisor(repository, max_workers=1)
    driver = ExperimentCoordinator(service, supervisor)
    manifest = compile_experiment(specification())

    def failure():
        raise OSError("injected usage failure")

    monkeypatch.setattr(repository, "usage_bytes", failure)
    try:
        driver.start(manifest)
        driver._thread.join(timeout=5)
        assert not driver._thread.is_alive()
        assert driver.error == "OSError: injected usage failure"
        assert service.summary(manifest["experiment_id"])["state"] == "failed"
    finally:
        driver.close()
        supervisor.close()
