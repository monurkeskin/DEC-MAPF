"""Durable experiment services shared by the headless CLI and GUI workspace."""
from __future__ import annotations

import threading
from collections import Counter
from typing import Any

from mapf.application._experiment_reporting import trial_row, trial_status
from mapf.application.experiment_execution import ExecutionOptions, ExperimentExecutor
from mapf.application.experiment_manifest import (
    ExperimentBudget,
    ExperimentSpec,
    compile_experiment,
    verify_manifest,
)
from mapf.application.experiment_store import ExperimentStore, SQLiteExperimentStore
from mapf.application.jobs import JobSupervisor
from mapf.application.runs import RunRepository

__all__ = [
    "ExperimentBudget",
    "ExperimentCoordinator",
    "ExperimentService",
    "ExperimentSpec",
    "compile_experiment",
    "verify_manifest",
]


class ExperimentService:
    """Expose frozen plans, execution and all-planned outcomes to CLI and HTTP.

    Persistence goes through ``ExperimentStore``; one invocation's admissions
    and cleanup belong to ``ExperimentExecutor``. This facade does not own a
    second worker pool or reinterpret solver success as physical validity.
    """

    def __init__(self, repository: RunRepository, *, store: ExperimentStore | None = None) -> None:
        self.repository = repository
        self.store: ExperimentStore = store if store is not None else SQLiteExperimentStore(repository)

    def get_manifest(self, experiment_id: str) -> dict[str, Any]:
        """Return the frozen manifest through the public persistence boundary."""
        return self.store.manifest(experiment_id)

    def _manifest(self, experiment_id: str) -> dict[str, Any]:
        """Convenience alias for the experiment outcome export."""
        return self.get_manifest(experiment_id)

    def manifests(self) -> list[dict[str, Any]]:
        return self.store.manifests()

    def attempts(self, experiment_id: str) -> dict[str, list[dict[str, Any]]]:
        return self.store.attempts(experiment_id)

    def rows(self, experiment_id: str) -> list[dict[str, Any]]:
        manifest = self.get_manifest(experiment_id)
        attempts = self.attempts(experiment_id)
        return [trial_row(self.repository, manifest, trial, attempts.get(trial["trial_id"], []))
                for trial in manifest["trials"]]

    def summary(self, experiment_id: str) -> dict[str, Any]:
        trial_ids = self.store.trial_ids(experiment_id)
        latest = self.store.latest_attempts(experiment_id)
        counts: Counter[str] = Counter()
        successes = 0
        for trial_id in trial_ids:
            status, success = trial_status(self.repository, latest.get(trial_id))
            successes += success
            counts[status] += 1
        state, elapsed = self.store.progress(experiment_id)
        result = {"experiment_id": experiment_id, "state": state, "planned": len(trial_ids),
                "counts": dict(counts), "successful": successes,
                "success_rate": successes / len(trial_ids), "elapsed_seconds": elapsed,
                "attempt_selection": "latest explicit attempt; complete attempt history retained"}
        resource_file = self.repository.base_dir / "resource-status.json"
        if resource_file.exists():
            import json
            result["workspace_resource_status"] = json.loads(resource_file.read_text())
        return result

    def register(self, manifest: dict[str, Any], *, resume: bool = False) -> float:
        verify_manifest(manifest)
        return self.store.register(manifest, resume=resume)

    def execute(self, manifest: dict[str, Any], *, resume: bool = False, retry_failed: bool = False,
                supervisor: JobSupervisor | None = None, stop: threading.Event | None = None) -> dict[str, Any]:
        executor = ExperimentExecutor(self.repository, self.store, manifest)
        executor.run(ExecutionOptions(resume=resume, retry_failed=retry_failed, stop=stop), supervisor)
        return self.summary(manifest["experiment_id"])

    def resume(self, experiment_id: str, *, retry_failed: bool = False) -> dict[str, Any]:
        return self.execute(self.get_manifest(experiment_id), resume=True, retry_failed=retry_failed)


class ExperimentCoordinator:
    """Optional UI driver using the same execution loop and existing process owner."""

    def __init__(self, service: ExperimentService, supervisor: JobSupervisor) -> None:
        self.service, self.supervisor = service, supervisor
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.active: str | None = None
        self.error: str | None = None

    def start(self, manifest: dict[str, Any], *, resume: bool = False, retry_failed: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ValueError("An experiment is already running in this workspace")
            self._check_capacity(manifest)
            self.service.register(manifest, resume=resume)
            self.active, self.error = manifest["experiment_id"], None
            self._stop.clear()
            self._thread = threading.Thread(target=self._execute, args=(manifest, retry_failed),
                                            name="mapf-experiment", daemon=True)
            self._thread.start()
            return {"experiment_id": self.active, "state": "admitted"}

    def _check_capacity(self, manifest: dict[str, Any]) -> None:
        budget = ExperimentBudget.model_validate(manifest["budget"])
        if budget.workers > self.supervisor.max_workers:
            raise ValueError("Experiment worker budget exceeds this workspace's worker limit")
        if budget.resources != self.supervisor.resource_policy:
            raise ValueError("Experiment resource policy must match the owning supervisor policy")
        if budget.disk_mb * 1024 * 1024 > self.service.repository.quota_bytes:
            raise ValueError("Experiment disk budget exceeds the workspace quota")

    def _execute(self, manifest: dict[str, Any], retry_failed: bool) -> None:
        try:
            self.service.execute(manifest, resume=True, retry_failed=retry_failed,
                                 supervisor=self.supervisor, stop=self._stop)
        except Exception as exc:  # noqa: BLE001 - surface background infrastructure failure
            self.error = f"{type(exc).__name__}: {exc}"

    def stop(self, experiment_id: str) -> dict[str, str]:
        """Stop only the selected experiment and report its durable final state."""
        with self._lock:
            if self.active != experiment_id:
                raise ValueError("This experiment is not active")
            self.close()
            return {
                "state": self.service.summary(experiment_id)["state"],
                "experiment_id": experiment_id,
            }

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                raise RuntimeError("Experiment driver did not stop within shutdown deadline")
