"""Frozen Cartesian experiments, durable attempts and headless bounded execution.

There is one supervisor/journal implementation for GUI jobs and experiments.
Resume reruns interrupted trials, never restores a speculative solver state.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.experiment_store import ExperimentStore, SQLiteExperimentStore
from mapf.application.jobs import JobSupervisor
from mapf.application.plans import preview, provenance
from mapf.application.presets import get_preset
from mapf.application.resources import ResourcePolicy, resource_kind
from mapf.application.runs import TERMINAL, RunRepository, digest


class ExperimentBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workers: int = Field(default=2, ge=1, le=6)
    wall_seconds: float = Field(default=900, ge=1, le=86400)
    max_trials: int = Field(default=10000, ge=1, le=100000)
    disk_mb: int = Field(default=2048, ge=64, le=65536)
    threads_per_worker: int = Field(default=1, ge=1, le=1)
    resources: ResourcePolicy | None = None

    @model_validator(mode="after")
    def check_worker_policy(self) -> ExperimentBudget:
        if self.resources is None and self.workers > 4:
            raise ValueError("More than four workers requires explicit resource admission")
        return self


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    scenarios: list[dict[str, Any]] = Field(min_length=1)
    defaults: dict[str, Any] = Field(default_factory=dict)
    preset_id: str | None = None
    matrix: dict[str, list[Any]] = Field(default_factory=dict)
    exclude: list[dict[str, Any]] = Field(default_factory=list)
    budget: ExperimentBudget = Field(default_factory=ExperimentBudget)
    sampling: dict[str, Any] = Field(default_factory=lambda: {
        "population": "declared fixtures only", "independent_unit": "instance_hash",
    })


def compile_experiment(raw: dict[str, Any], repository: RunRepository | None = None) -> dict[str, Any]:
    spec = ExperimentSpec.model_validate(raw)
    fields = set(JobSubmissionRequest.model_fields)
    if set(spec.matrix) - fields or any(set(e) - fields for e in spec.exclude):
        raise ValueError("Unknown matrix/exclusion parameter")
    if any(not values for values in spec.matrix.values()):
        raise ValueError("Each matrix axis needs at least one value")
    keys = sorted(spec.matrix)
    count = len(spec.scenarios)
    for key in keys:
        count *= len(spec.matrix[key])
    if count > spec.budget.max_trials:
        raise ValueError("Cartesian expansion exceeds max_trials (before exclusions)")
    source = provenance()
    preset = get_preset(spec.preset_id).inputs.model_dump() if spec.preset_id else {}
    trials: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for scenario_index, scenario in enumerate(spec.scenarios):
        for combination in itertools.product(*(spec.matrix[k] for k in keys)):
            effective = {**preset, **spec.defaults, **scenario, **dict(zip(keys, combination, strict=True))}
            sampling_unit = effective.pop("sampling_unit", None)
            matches = [i for i, rule in enumerate(spec.exclude)
                       if all(effective.get(key) == value for key, value in rule.items())]
            if matches:
                excluded.append({"scenario_index": scenario_index, "inputs": effective, "rule_indices": matches})
                continue
            request = JobSubmissionRequest.model_validate(effective)
            plan = preview(request, repository)
            plan["provenance"] = {key: value for key, value in source.items() if key != "source_files"}
            # Identity includes the source as well as the complete effective input.
            identity = digest({"definition": plan["definition_digest"], "source": source["source_sha256"]})
            trial_id = digest({"identity": identity, "ordinal": len(trials)})
            trials.append({"trial_id": trial_id, "definition_identity": identity,
                           "scenario_index": scenario_index, "plan": plan,
                           "sampling_unit": sampling_unit or digest({key: plan["scenario"][key] for key in
                               ("grid_width", "grid_height", "starts", "goals", "obstacles")})})
    if not trials:
        raise ValueError("All experiment trials were excluded")
    limits = [t["plan"]["effective_config"]["timeout_sec"] for t in trials]
    body = {"schema_version": "experiment-1", "name": spec.name, "sampling": spec.sampling,
            "budget": spec.budget.model_dump(), "trials": trials, "excluded": excluded,
            "source_sha256": source["source_sha256"], "provenance": source,
            "maximum_process_seconds": None if any(t is None for t in limits) else sum(limits)}
    if spec.preset_id:
        body["preset_id"] = spec.preset_id
    checksum = digest(body)
    return {**body, "manifest_digest": checksum, "experiment_id": "experiment-" + checksum[:24]}


def verify_manifest(manifest: dict[str, Any], *, check_source: bool = True) -> None:
    body = {k: v for k, v in manifest.items() if k not in ("manifest_digest", "experiment_id")}
    if digest(body) != manifest.get("manifest_digest"):
        raise ValueError("Experiment manifest digest mismatch")
    if manifest.get("experiment_id") != "experiment-" + digest(body)[:24]:
        raise ValueError("Experiment identity does not match its digest")
    ExperimentBudget.model_validate(manifest["budget"])
    if check_source and provenance()["source_sha256"] != manifest["source_sha256"]:
        raise ValueError("Source changed since planning; freeze a new experiment manifest")


class ExperimentService:
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
        rows = []
        for trial in manifest["trials"]:
            history = attempts.get(trial["trial_id"], [])
            job = history[-1] if history else None
            plan = trial["plan"]
            row = {"trial_id": trial["trial_id"], "experiment_id": experiment_id,
                   "instance_hash": plan["scenario"]["instance_hash"],
                   "definition_identity": trial["definition_identity"],
                   "source_sha256": manifest["source_sha256"], "attempt_count": len(history),
                   "sampling_unit": trial["sampling_unit"],
                   "state": job["state"] if job else "not_admitted",
                   "job_id": job["job_id"] if job else None, "run_id": job["run_id"] if job else None,
                   "success": False, "sum_of_costs": None, "makespan": None, "runtime_ms": None,
                   "validation_status": "not_checked", "metric_version": plan["provenance"]["metric_version"],
                   "agent_count": len(plan["scenario"]["starts"]), "grid_width": plan["scenario"]["grid_width"],
                   "grid_height": plan["scenario"]["grid_height"],
                   "error": job.get("error") if job else None, **plan["effective_config"]}
            if job and job["state"] == "completed":
                run = self.repository.get_run(job["run_id"], include_frames=False)
                if run is None:
                    row.update(state="artifact_missing", error="Completed trial artifact was deleted")
                else:
                    result = run["result"]
                    row.update(success=result["success"], validation_status=result["validation"]["status"],
                               sum_of_costs=result["sum_of_costs"] if result["success"] else None,
                               makespan=result["makespan"] if result["success"] else None,
                               runtime_ms=result["runtime_ms"], information_sharing_rate=result["information_sharing_rate"],
                               norm_path_diff=result["norm_path_diff"], **result.get("measured_metrics", {}))
            rows.append(row)
        return rows

    def summary(self, experiment_id: str) -> dict[str, Any]:
        trial_ids = self.store.trial_ids(experiment_id)
        latest = self.store.latest_attempts(experiment_id)
        counts: Counter[str] = Counter()
        successes = 0
        for trial_id in trial_ids:
            job = latest.get(trial_id)
            status = job["state"] if job else "not_admitted"
            if job and status == "completed":
                success = self.repository.verified_success(job["run_id"], job["artifact_sha256"])
                if success is None:
                    status = "artifact_missing"
                else:
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
        budget = ExperimentBudget.model_validate(manifest["budget"])
        if supervisor is not None:
            if budget.workers > supervisor.max_workers:
                raise ValueError("Experiment worker budget exceeds the active workspace worker limit")
            if budget.resources != supervisor.resource_policy:
                raise ValueError("Experiment resource policy must match the owning supervisor policy")
        verify_manifest(manifest)
        owns_supervisor = supervisor is None
        if owns_supervisor:
            supervisor = JobSupervisor(self.repository, max_workers=budget.workers, resource_policy=budget.resources)
        assert supervisor is not None
        try:
            elapsed = self.register(manifest, resume=resume)
        except BaseException:
            if owns_supervisor:
                supervisor.close()
            raise
        eid = manifest["experiment_id"]
        if owns_supervisor:
            self.repository.quota_bytes = budget.disk_mb * 1024 * 1024
        started = time.monotonic()
        status = "completed"
        # At most one new attempt per trial in this invocation. Failed trials do not
        # spin forever, and infrastructure errors remain in the denominator.
        submitted: set[str] = set()
        try:
            while True:
                if stop is not None and stop.is_set():
                    status = "interrupted"
                    break
                if hasattr(supervisor, "last_error"):
                    raise RuntimeError(supervisor.last_error)
                charged = elapsed + time.monotonic() - started
                self.store.update(eid, "running", charged)
                if charged >= budget.wall_seconds:
                    status = "budget_exhausted"
                    break
                if self.repository.usage_bytes() >= budget.disk_mb * 1024 * 1024:
                    status = "budget_exhausted"
                    break
                if supervisor.admission is not None and supervisor.admission.idle_exhausted():
                    status = "resource_blocked"
                    break
                latest = self.store.latest_attempts(eid)
                if any("Source changed" in (h.get("error") or "") for h in latest.values()):
                    raise ValueError("Source changed during execution; remaining trials were not admitted")
                active = sum(h["state"] not in TERMINAL for h in latest.values())
                eligible = []
                for trial in manifest["trials"]:
                    tid = trial["trial_id"]
                    last = latest.get(tid)
                    if tid in submitted:
                        continue
                    if last is None or (resume and last["state"] == "interrupted") or (
                        retry_failed and last["state"] in {"failed", "timed_out", "cancelled"}
                    ):
                        eligible.append((trial, last))
                # Shared GUI/CLI supervisor, with this experiment's own concurrency cap.
                room = max(0, min(budget.workers - active,
                                 supervisor.max_pending - len(self.repository.active_jobs())))
                if budget.resources is not None:
                    # Fill a bounded mixed-family window, so a memory-heavy head
                    # cannot hide an eligible lightweight trial farther behind it.
                    central = [item for item in eligible if resource_kind(item[0]["plan"]) != "decentralized"]
                    decentral = [item for item in eligible if resource_kind(item[0]["plan"]) == "decentralized"]
                    eligible = [item for pair in itertools.zip_longest(central, decentral) for item in pair if item is not None]
                    room = max(0, supervisor.max_pending - len(self.repository.active_jobs()))
                for trial, last in eligible[:room]:
                    index = last["attempt_count"] if last else 0
                    supervisor.submit_plan(trial["plan"], f"{eid}:{trial['trial_id'][:32]}:{index}",
                                           experiment_id=eid, trial_id=trial["trial_id"], attempt_index=index,
                                           experiment_worker_limit=budget.workers,
                                           parent_job_id=last["job_id"] if last else None)
                    submitted.add(trial["trial_id"])
                    active += 1
                if active == 0 and not eligible:
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            status = "interrupted"
        except BaseException:
            status = "failed"
            raise
        finally:
            if owns_supervisor:
                supervisor.close()
            else:
                for job in self.repository.active_jobs():
                    if job.get("experiment_id") == eid:
                        supervisor.interrupt_job(job["job_id"])
            charged = elapsed + time.monotonic() - started
            self.store.update(eid, status, charged)
        return self.summary(eid)

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
            budget = ExperimentBudget.model_validate(manifest["budget"])
            if budget.workers > self.supervisor.max_workers:
                raise ValueError("Experiment worker budget exceeds this workspace's worker limit")
            if budget.resources != self.supervisor.resource_policy:
                raise ValueError("Experiment resource policy must match the owning supervisor policy")
            if budget.disk_mb * 1024 * 1024 > self.service.repository.quota_bytes:
                raise ValueError("Experiment disk budget exceeds the workspace quota")
            self.service.register(manifest, resume=resume)
            self.active, self.error = manifest["experiment_id"], None
            self._stop.clear()
            def execute() -> None:
                try:
                    self.service.execute(manifest, resume=True, retry_failed=retry_failed,
                                         supervisor=self.supervisor, stop=self._stop)
                except Exception as exc:  # noqa: BLE001 - surface background infrastructure failure
                    self.error = f"{type(exc).__name__}: {exc}"
            self._thread = threading.Thread(target=execute, name="mapf-experiment", daemon=True)
            self._thread.start()
            return {"experiment_id": self.active, "state": "admitted"}

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=15)
            if self._thread.is_alive():
                raise RuntimeError("Experiment driver did not stop within shutdown deadline")
