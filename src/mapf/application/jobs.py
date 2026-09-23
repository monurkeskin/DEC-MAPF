"""Bounded process supervisor with durable admission, cancellation and recovery."""

from __future__ import annotations

import fcntl
import json
import multiprocessing
import threading
import time
from collections.abc import Callable
from enum import Enum
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.deadlines import NegotiationWatch
from mapf.application.native_diagnostics import diagnostic_path, read_diagnostics
from mapf.application.plans import preview, provenance
from mapf.application.processes import run_owned_process, stop_owned_group
from mapf.application.resources import ResourceAdmission, ResourcePolicy, ResourceProbe
from mapf.application.runs import (
    TERMINAL,
    RunRepository,
    atomic_write,
    digest,
    encode,
    new_id,
)
from mapf.application.worker import owned_worker

OwnedWorker = tuple[BaseProcess, float | None, Any, NegotiationWatch]


def _validate_command_key(command_key: str | None) -> None:
    if not command_key:
        return
    if len(command_key) > 128 or not command_key.strip():
        raise ValueError("Idempotency-Key must contain 1 to 128 characters")


def _read_worker_result(stage: Path, exitcode: int | None) -> dict[str, Any]:
    """Accept a bounded, committed result only after a successful worker exit."""
    if exitcode != 0 or not stage.exists():
        raise RuntimeError(f"Worker exited without a committed result (exit={exitcode})")
    if stage.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Worker artifact exceeds the supported size")
    execution: dict[str, Any] = json.loads(stage.read_text())
    if not execution["ok"]:
        raise RuntimeError(execution["error"])
    return execution


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"


def completed_payload(job: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
    result = execution["result"]
    result["run_id"] = job["run_id"]
    snap = job["plan"]["scenario"]
    validation = result["validation"]
    timestamp = time.time()
    return {
        "schema_version": "1.0",
        "metadata": {
            "run_id": job["run_id"],
            "attempt_id": job["attempt_id"],
            "job_id": job["job_id"],
            "definition_digest": job["definition_digest"],
            "instance_hash": snap["instance_hash"],
            "solver_name": result["solver"],
            "setting": snap["setting"],
            "agent_count": len(snap["starts"]),
            "grid_width": snap["grid_width"],
            "grid_height": snap["grid_height"],
            "success": result["success"],
            "is_valid": validation["is_valid"],
            "validation_status": validation["status"],
            "validation_errors": validation["errors"],
            "execution_status": "completed",
            "solver_outcome": result["solver_outcome"],
            "makespan": result["makespan"],
            "sum_of_costs": result["sum_of_costs"],
            "runtime_ms": result["runtime_ms"],
            "frame_count": len(result["frames"]),
            "timestamp": timestamp,
            "effective_config": job["effective_config"],
            "instance": snap,
            "provenance": job["plan"]["provenance"],
            "metric_version": job["plan"]["provenance"]["metric_version"],
            "experiment_id": job.get("experiment_id"),
            "trial_id": job.get("trial_id"),
            "parent_job_id": job.get("parent_job_id"),
            "timings": dict(
                execution["timings"],
                queue_ms=(job["started_at"] - job["created_at"]) * 1000,
                process_wall_ms=(timestamp - job["started_at"]) * 1000,
            ),
            "trace": execution["trace"],
            "legacy_metrics": execution["legacy_metrics"],
            "measured_metrics": execution.get("measured_metrics", {}),
            "execution_thread_limits": execution.get("execution_thread_limits", {}),
            "resource_admission": job.get("resource_admission"),
        },
        "result": result,
        "frames": result["frames"],
    }


class JobSupervisor:
    """One owner per data directory; no executor or filesystem globals at import."""

    def __init__(
        self,
        repository: RunRepository,
        max_workers: int = 2,
        max_pending: int = 32,
        worker: Callable[..., None] = owned_worker,
        *,
        resource_policy: ResourcePolicy | None = None,
        resource_probe: ResourceProbe | None = None,
    ) -> None:
        limit = 6 if resource_policy is not None else 4
        if not 1 <= max_workers <= limit:
            raise ValueError(f"Local worker count must be 1 to {limit}")
        self.repository = repository
        self.resource_policy = resource_policy
        self.admission = ResourceAdmission(resource_policy, resource_probe) if resource_policy is not None else None
        self._resource_written_at = float("-inf")
        self.max_workers = max_workers
        self.max_pending = max_pending
        self.worker = worker
        self._mutex = threading.RLock()
        self._stop = threading.Event()
        self._processes: dict[str, OwnedWorker] = {}
        self._lease = (repository.base_dir / "supervisor.lock").open("a+")
        try:
            fcntl.flock(self._lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lease.close()
            raise RuntimeError(
                "A supervisor already owns this workspace directory"
            ) from None
        try:
            self.repository.recover()
            self._context = multiprocessing.get_context("spawn")
            self._thread = threading.Thread(
                target=self._monitor, name="mapf-supervisor", daemon=True
            )
            self._thread.start()
        except BaseException:
            fcntl.flock(self._lease.fileno(), fcntl.LOCK_UN)
            self._lease.close()
            raise

    def submit(
        self,
        request: JobSubmissionRequest,
        command_key: str | None = None,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        _validate_command_key(command_key)
        job = self._prepare(request, batch_id)
        with self._mutex:
            if self._stop.is_set():
                raise RuntimeError("Supervisor is shutting down")
            job, _created = self.repository.admit(
                job,
                command_key,
                digest(request.model_dump(mode="json")),
                self.max_pending,
            )
        return job

    def _prepare(
        self, request: JobSubmissionRequest, batch_id: str | None = None
    ) -> dict[str, Any]:
        plan = preview(request, self.repository)
        plan["provenance"] = provenance()
        now = time.time()
        job = {
            "job_id": new_id("job"),
            "run_id": new_id("run"),
            "attempt_id": new_id("attempt"),
            "definition_digest": plan["definition_digest"],
            "solver_id": plan["effective_config"]["solver_id"],
            "state": "pending",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": None,
            "worker_pid": None,
            "batch_id": batch_id,
            "effective_config": plan["effective_config"],
            "plan": plan,
        }
        return job

    def submit_batch(
        self, requests: list[JobSubmissionRequest], command_key: str, plan_digest: str
    ) -> dict[str, Any]:
        from mapf.application.plans import preview_batch

        if not 1 <= len(command_key.strip()) <= 128:
            raise ValueError("Idempotency-Key must contain 1 to 128 characters")
        if preview_batch(requests, self.repository)["plan_digest"] != plan_digest:
            raise ValueError("Plan changed; preview the exact effective inputs again")
        batch_id = new_id("batch")
        jobs = [self._prepare(req, batch_id) for req in requests]
        with self._mutex:
            if self._stop.is_set():
                raise RuntimeError("Supervisor is shutting down")
            return self.repository.admit_batch(
                jobs, command_key, plan_digest, self.max_pending
            )

    def submit_plan(self, plan: dict[str, Any], command_key: str, **identity: Any) -> dict[str, Any]:
        """Admit a previously frozen experiment definition through the same journal."""
        now = time.time()
        job = {
            "job_id": new_id("job"), "run_id": new_id("run"), "attempt_id": new_id("attempt"),
            "definition_digest": plan["definition_digest"], "solver_id": plan["effective_config"]["solver_id"],
            "state": "pending", "created_at": now, "started_at": None, "completed_at": None,
            "error": None, "result": None, "worker_pid": None, "batch_id": None,
            "effective_config": plan["effective_config"], "plan": plan, **identity,
        }
        with self._mutex:
            if self._stop.is_set():
                raise RuntimeError("Supervisor is shutting down")
            admitted, _ = self.repository.admit(job, command_key, digest(plan), self.max_pending)
            return admitted

    def retry(self, job_id: str) -> dict[str, Any]:
        parent = self.repository.get_job(job_id)
        if parent is None:
            raise KeyError(job_id)
        if parent["state"] not in TERMINAL:
            raise ValueError("Only a terminal job can be retried")
        if parent["plan"]["provenance"]["source_sha256"] != provenance()["source_sha256"]:
            raise ValueError("Retry requires the original source identity")
        return self.submit_plan(parent["plan"], new_id("attempt"), parent_job_id=job_id)

    def interrupt_job(self, job_id: str) -> bool:
        return self.cancel_job(job_id, interrupted=True)

    def cancel_job(self, job_id: str, *, interrupted: bool = False) -> bool:
        with self._mutex:
            job = self.repository.get_job(job_id)
            if job is None:
                raise KeyError(job_id)
            if job["state"] in TERMINAL:
                return False
            owned = self._processes.pop(job_id, None)
            if owned:
                self._terminate(owned)
            self.repository.transition(job_id, "interrupted" if interrupted else "cancelled")
            (self.repository.staging / f"{job['attempt_id']}.json").unlink(
                missing_ok=True
            )
            return True

    @staticmethod
    def _terminate(owned: OwnedWorker) -> None:
        proc, _, sender, _ = owned
        if proc.pid is not None:
            stop_owned_group(proc.pid)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=0.5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=1)
        if proc.is_alive():
            raise RuntimeError("Owned worker did not stop within cancellation deadline")
        proc.join()
        proc.close()
        sender.close()

    def _monitor(self) -> None:
        while not self._stop.wait(0.05):
            try:
                with self._mutex:
                    self._cycle()
            except Exception as exc:  # noqa: BLE001 - isolation boundary records infrastructure failure
                with self._mutex:
                    self._fail_active(exc)

    def _fail_active(self, exc: Exception) -> None:
        self.last_error = f"{type(exc).__name__}: {exc}"
        for job in self.repository.active_jobs():
            if job["state"] in TERMINAL:
                continue
            try:
                owned = self._processes.pop(job["job_id"], None)
                if owned:
                    self._terminate(owned)
                self.repository.transition(job["job_id"], "failed", error=self.last_error)
            except Exception:  # noqa: BLE001 - preserve degraded health when the journal is unavailable
                self._stop.set()

    def _cycle(self) -> None:
        for job_id, owned in list(self._processes.items()):
            job = self.repository.get_job(job_id)
            assert job is not None
            self._observe_worker(job, owned)
        for job in self._select_jobs():
            self._start_worker(job)

    @staticmethod
    def _drain_notifications(sender: Any, negotiation: NegotiationWatch) -> None:
        # Bound draining so a busy child cannot starve deadline/cancel checks.
        for _ in range(128):
            if not sender.poll():
                break
            try:
                negotiation.receive(sender.recv())
            except EOFError:
                break

    def _observe_worker(self, job: dict[str, Any], owned: OwnedWorker) -> None:
        proc, deadline, sender, negotiation = owned
        self._drain_notifications(sender, negotiation)
        if negotiation.expired(time.monotonic()):
            self._negotiation_timed_out(job, owned)
        elif not proc.is_alive():
            self._finish_worker(job, owned)
        elif deadline is not None and time.monotonic() >= deadline:
            self._process_timed_out(job, owned)

    def _staging_path(self, job: dict[str, Any]) -> Path:
        return self.repository.staging / f"{job['attempt_id']}.json"

    def _negotiation_timed_out(self, job: dict[str, Any], owned: OwnedWorker) -> None:
        self._terminate(owned)
        del self._processes[job["job_id"]]
        negotiation = owned[3]
        self.repository.transition(job["job_id"], "timed_out", timeout_scope="negotiation",
            timeout_session_id=negotiation.session_id,
            timeout_diagnostics=negotiation.timeout_diagnostics(time.monotonic()),
            error="Bilateral negotiation wall-clock deadline exhausted; no complete solution receipt")
        self._staging_path(job).unlink(missing_ok=True)

    def _process_timed_out(self, job: dict[str, Any], owned: OwnedWorker) -> None:
        self._terminate(owned)
        del self._processes[job["job_id"]]
        self.repository.transition(job["job_id"], "timed_out", timeout_scope="process",
            timeout_diagnostics=read_diagnostics(self._staging_path(job), job),
            error="Process wall-clock budget exhausted; no complete solution receipt")
        self._staging_path(job).unlink(missing_ok=True)
        diagnostic_path(self._staging_path(job)).unlink(missing_ok=True)

    def _finish_worker(self, job: dict[str, Any], owned: OwnedWorker) -> None:
        proc, _, sender, _ = owned
        if proc.pid is not None:
            stop_owned_group(proc.pid)
        proc.join()
        exitcode = proc.exitcode
        proc.close()
        sender.close()
        del self._processes[job["job_id"]]
        self._publish_stage(job, exitcode)

    def _publish_stage(self, job: dict[str, Any], exitcode: int | None) -> None:
        stage = self._staging_path(job)
        try:
            execution = _read_worker_result(stage, exitcode)
            self.repository.save_run(completed_payload(job, execution), job["job_id"])
        except Exception as exc:  # noqa: BLE001 - isolation boundary records rejected worker artifacts
            self.repository.transition(job["job_id"], "failed", error=f"{type(exc).__name__}: {exc}",
                                       solver_diagnostics=read_diagnostics(stage, job))
        finally:
            stage.unlink(missing_ok=True)
            diagnostic_path(stage).unlink(missing_ok=True)

    def _select_jobs(self) -> list[dict[str, Any]]:
        waiting = [job for job in self.repository.active_jobs() if job["state"] == "pending"]
        slots = max(0, self.max_workers - len(self._processes))
        if self.admission is None:
            return waiting[:slots]
        running = [job for job in self.repository.active_jobs() if job["job_id"] in self._processes]
        processes = {jid: owned[0].pid for jid, owned in self._processes.items() if owned[0].pid is not None}
        selected = self.admission.choose(waiting, running, processes, slots)
        if time.monotonic() - self._resource_written_at >= 1 or selected:
            atomic_write(self.repository.base_dir / "resource-status.json", encode(self.admission.latest))
            self._resource_written_at = time.monotonic()
        return selected

    def _start_worker(self, job: dict[str, Any]) -> None:
        recv, sender = self._context.Pipe(duplex=True)
        proc = self._context.Process(target=run_owned_process,
            args=(self.worker, job, str(self._staging_path(job)), recv), daemon=True)
        try:
            proc.start()
        except Exception:
            recv.close()
            sender.close()
            proc.close()
            raise
        recv.close()
        timeout = job["effective_config"]["timeout_sec"]
        self._processes[job["job_id"]] = (proc,
            time.monotonic() + timeout if timeout is not None else None, sender, NegotiationWatch())
        self.repository.transition(job["job_id"], "running", started_at=time.time(), worker_pid=proc.pid,
            resource_admission=self.admission.latest if self.admission is not None else None)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)
        with self._mutex:
            for owned in self._processes.values():
                self._terminate(owned)
            self._processes.clear()
            try:
                for job in self.repository.active_jobs():
                    if job["state"] not in TERMINAL:
                        self.repository.transition(job["job_id"], "interrupted", error="Application shutdown")
            finally:
                # Processes have stopped; a journal error must not retain a dead
                # owner's lease. The exception still propagates to the caller.
                fcntl.flock(self._lease.fileno(), fcntl.LOCK_UN)
                self._lease.close()
