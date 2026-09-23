"""The UI driver admits one experiment and makes incomplete shutdown explicit."""

import threading
from unittest.mock import Mock

import pytest

from mapf.application.experiments import (
    ExperimentCoordinator,
    ExperimentService,
    compile_experiment,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.runs import RunRepository
from tests.test_experiment_guards import specification


def test_running_driver_rejects_a_second_manifest_without_replacing_the_first(tmp_path, monkeypatch):
    service = ExperimentService(RunRepository(tmp_path))
    owner = JobSupervisor(service.repository)
    driver = ExperimentCoordinator(service, owner)
    entered, release = threading.Event(), threading.Event()

    def paused_execution(*args, **kwargs):
        entered.set()
        assert release.wait(5), "Test driver was not released"

    monkeypatch.setattr(service, "execute", paused_execution)
    first = compile_experiment(specification())
    second = compile_experiment(specification(name="another experiment"))
    try:
        driver.start(first)
        assert entered.wait(2)
        with pytest.raises(ValueError, match="already running"):
            driver.start(second)
        assert driver.active == first["experiment_id"]
        assert [m["experiment_id"] for m in service.manifests()] == [first["experiment_id"]]
    finally:
        release.set()
        driver.close()
        owner.close()


def test_driver_reports_a_thread_that_survives_the_shutdown_deadline(tmp_path):
    # Inject the outcome of a failed bounded join without delaying the test by 15 seconds.
    service = ExperimentService(RunRepository(tmp_path))
    driver = ExperimentCoordinator(service, Mock(spec=JobSupervisor))
    driver._thread = Mock()
    driver._thread.is_alive.return_value = True
    with pytest.raises(RuntimeError, match="shutdown deadline"):
        driver.close()
    assert driver._stop.is_set()
    driver._thread.join.assert_called_once_with(timeout=15)
