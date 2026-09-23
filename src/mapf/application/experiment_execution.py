"""Bounded experiment scheduling over the existing owned-process supervisor."""
from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass
from typing import Any

from mapf.application.experiment_manifest import ExperimentBudget, verify_manifest
from mapf.application.experiment_store import ExperimentStore
from mapf.application.jobs import JobSupervisor
from mapf.application.resources import resource_kind
from mapf.application.runs import TERMINAL, RunRepository

TrialAttempt = tuple[dict[str, Any], dict[str, Any] | None]


@dataclass(frozen=True)
class ExecutionOptions:
    resume: bool = False
    retry_failed: bool = False
    stop: threading.Event | None = None

    def eligible(self, last: dict[str, Any] | None) -> bool:
        if last is None:
            return True
        if self.resume and last["state"] == "interrupted":
            return True
        return self.retry_failed and last["state"] in {"failed", "timed_out", "cancelled"}


class ExperimentExecutor:
    """Own one invocation's budget, admissions and cleanup, never a solver state."""

    def __init__(self, repository: RunRepository, store: ExperimentStore, manifest: dict[str, Any]) -> None:
        self.repository, self.store, self.manifest = repository, store, manifest
        self.budget = ExperimentBudget.model_validate(manifest["budget"])
        self.experiment_id = manifest["experiment_id"]
        self.submitted: set[str] = set()

    def run(self, options: ExecutionOptions, supervisor: JobSupervisor | None) -> None:
        self.options = options
        self._check_supervisor(supervisor)
        verify_manifest(self.manifest)
        self.owns_supervisor = supervisor is None
        self.supervisor = supervisor if supervisor is not None else JobSupervisor(
            self.repository, max_workers=self.budget.workers, resource_policy=self.budget.resources)
        self._register()
        if self.owns_supervisor:
            self.repository.quota_bytes = self.budget.disk_mb * 1024 * 1024
        self.started = time.monotonic()
        status = "completed"
        try:
            status = self._drive()
        except KeyboardInterrupt:
            status = "interrupted"
        except BaseException:
            status = "failed"
            raise
        finally:
            self._close(status)

    def _check_supervisor(self, supervisor: JobSupervisor | None) -> None:
        if supervisor is None:
            return
        if self.budget.workers > supervisor.max_workers:
            raise ValueError("Experiment worker budget exceeds the active workspace worker limit")
        if self.budget.resources != supervisor.resource_policy:
            raise ValueError("Experiment resource policy must match the owning supervisor policy")

    def _register(self) -> None:
        try:
            verify_manifest(self.manifest)
            self.elapsed = self.store.register(self.manifest, resume=self.options.resume)
        except BaseException:
            if self.owns_supervisor:
                self.supervisor.close()
            raise

    def _drive(self) -> str:
        while True:
            reason = self._stop_reason()
            if reason is not None:
                return reason
            if self._admit_cycle():
                return "completed"
            time.sleep(0.1)

    def _stop_reason(self) -> str | None:
        if self.options.stop is not None and self.options.stop.is_set():
            return "interrupted"
        if hasattr(self.supervisor, "last_error"):
            raise RuntimeError(self.supervisor.last_error)
        charged = self.elapsed + time.monotonic() - self.started
        self.store.update(self.experiment_id, "running", charged)
        if charged >= self.budget.wall_seconds:
            return "budget_exhausted"
        if self.repository.usage_bytes() >= self.budget.disk_mb * 1024 * 1024:
            return "budget_exhausted"
        admission = self.supervisor.admission
        if admission is not None and admission.idle_exhausted():
            return "resource_blocked"
        return None

    def _eligible(self, latest: dict[str, dict[str, Any]]) -> list[TrialAttempt]:
        trials: list[TrialAttempt] = []
        for trial in self.manifest["trials"]:
            tid = trial["trial_id"]
            if tid not in self.submitted and self.options.eligible(latest.get(tid)):
                trials.append((trial, latest.get(tid)))
        return trials

    def _window(self, eligible: list[TrialAttempt], active: int) -> tuple[list[TrialAttempt], int]:
        pending_room = self.supervisor.max_pending - len(self.repository.active_jobs())
        if self.budget.resources is None:
            return eligible, max(0, min(self.budget.workers - active, pending_room))
        # A bounded mixed-family window prevents a memory-heavy head from
        # hiding a lightweight trial that can fit the current resources.
        central: list[TrialAttempt] = []
        decentral: list[TrialAttempt] = []
        for item in eligible:
            group = decentral if resource_kind(item[0]["plan"]) == "decentralized" else central
            group.append(item)
        mixed = [item for pair in itertools.zip_longest(central, decentral) for item in pair if item is not None]
        return mixed, max(0, pending_room)

    def _admit_cycle(self) -> bool:
        latest = self.store.latest_attempts(self.experiment_id)
        if any("Source changed" in (history.get("error") or "") for history in latest.values()):
            raise ValueError("Source changed during execution; remaining trials were not admitted")
        active = sum(history["state"] not in TERMINAL for history in latest.values())
        eligible, room = self._window(self._eligible(latest), active)
        for trial, last in eligible[:room]:
            self._submit(trial, last)
            active += 1
        return active == 0 and not eligible

    def _submit(self, trial: dict[str, Any], last: dict[str, Any] | None) -> None:
        index = last["attempt_count"] if last else 0
        eid, tid = self.experiment_id, trial["trial_id"]
        self.supervisor.submit_plan(trial["plan"], f"{eid}:{tid[:32]}:{index}",
            experiment_id=eid, trial_id=tid, attempt_index=index,
            experiment_worker_limit=self.budget.workers, parent_job_id=last["job_id"] if last else None)
        # At most one new attempt per trial in this invocation. Failures remain
        # in the denominator and cannot trigger an unbounded retry loop.
        self.submitted.add(tid)

    def _close(self, status: str) -> None:
        try:
            self._stop_jobs()
        except BaseException:
            status = "failed"
            raise
        finally:
            charged = self.elapsed + time.monotonic() - self.started
            self.store.update(self.experiment_id, status, charged)

    def _stop_jobs(self) -> None:
        if self.owns_supervisor:
            self.supervisor.close()
        else:
            for job in self.repository.active_jobs():
                if job.get("experiment_id") == self.experiment_id:
                    self.supervisor.interrupt_job(job["job_id"])
