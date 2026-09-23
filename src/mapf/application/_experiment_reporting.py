"""Read-only projections of complete trial populations and artifact outcomes."""
from __future__ import annotations

from typing import Any

from mapf.application.runs import RunRepository


def trial_row(repository: RunRepository, manifest: dict[str, Any],
              trial: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    job = history[-1] if history else None
    plan = trial["plan"]
    row = {"trial_id": trial["trial_id"], "experiment_id": manifest["experiment_id"],
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
        _completed_row(repository, row, job)
    return row


def _completed_row(repository: RunRepository, row: dict[str, Any], job: dict[str, Any]) -> None:
    try:
        run = repository.get_run(job["run_id"], include_frames=False)
    except FileNotFoundError:
        run = None
    if run is None:
        row.update(state="artifact_missing", error="Completed trial artifact was deleted")
        return
    result = run["result"]
    row.update(success=result["success"], validation_status=result["validation"]["status"],
        sum_of_costs=result["sum_of_costs"] if result["success"] else None,
        makespan=result["makespan"] if result["success"] else None,
        runtime_ms=result["runtime_ms"], information_sharing_rate=result["information_sharing_rate"],
        norm_path_diff=result["norm_path_diff"], **result.get("measured_metrics", {}))


def trial_status(repository: RunRepository, job: dict[str, Any] | None) -> tuple[str, bool]:
    if job is None:
        return "not_admitted", False
    if job["state"] != "completed":
        return job["state"], False
    success = repository.verified_success(job["run_id"], job["artifact_sha256"])
    return ("artifact_missing", False) if success is None else ("completed", success)
