"""HTTP routes for workspace jobs; execution stays in application services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from mapf.application.contracts import (
    JobEvent,
    JobStatusResponse,
    JobSubmissionRequest,
    PlanAdmission,
    PlanRequest,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.plans import (
    preview_batch,
)
from mapf.application.responses import (
    PlanResponse,
)
from mapf.application.runs import RunRepository
from mapf.gui._event_stream import journal_events, replay_cursor


def register(
    api: APIRouter, services: Callable[[], tuple[RunRepository, JobSupervisor]]
) -> None:
    @api.post("/plans/preview", response_model=PlanResponse)
    def plan(request: PlanRequest) -> dict[str, Any]:
        repo, supervisor = services()
        return {
            **preview_batch(request.jobs, repo),
            "max_concurrency": supervisor.max_workers,
        }

    @api.post("/jobs", status_code=202, response_model=JobStatusResponse)
    def submit(
        request: JobSubmissionRequest,
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            return services()[1].submit(request, idempotency_key)
        except ValueError as exc:
            if "Idempotency key" in str(exc):
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            raise

    @api.get("/jobs")
    def jobs(limit: int = Query(default=100, ge=1, le=100)) -> list[dict[str, Any]]:
        return [
            {k: v for k, v in j.items() if k != "plan"}
            for j in services()[0].list_jobs(limit)
        ]

    @api.get("/jobs/{job_id}", response_model=JobStatusResponse)
    def job(job_id: str) -> dict[str, Any]:
        result = services()[0].get_job(job_id)
        if result is None:
            raise KeyError(job_id)
        return result

    @api.post("/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        repo, supervisor = services()
        changed = supervisor.cancel_job(job_id)
        state = repo.get_job(job_id)
        assert state is not None
        return {"cancelled": changed, "job_id": job_id, "state": state["state"]}

    @api.post("/jobs/{job_id}/retry", response_model=JobStatusResponse, status_code=202)
    def retry(job_id: str) -> dict[str, Any]:
        return services()[1].retry(job_id)

    @api.get("/jobs/{job_id}/events", response_model=list[JobEvent])
    def journal(
        job_id: str, cursor: int = Query(default=0, ge=0)
    ) -> list[dict[str, Any]]:
        job(job_id)
        return services()[0].events(job_id, cursor)

    @api.get("/jobs/{job_id}/stream")
    async def stream(
        job_id: str,
        request: Request,
        last_event_id: str | None = Header(default=None),
        cursor: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        repo, _ = services()
        job(job_id)
        cursor = replay_cursor(last_event_id, cursor, len(repo.events(job_id)))
        return StreamingResponse(
            journal_events(repo, job_id, request, cursor),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @api.post("/batches", status_code=202)
    def batch(
        request: PlanAdmission, idempotency_key: str = Header()
    ) -> dict[str, Any]:
        try:
            return services()[1].submit_batch(
                request.jobs, idempotency_key, request.plan_digest
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @api.post("/batches/{batch_id}/cancel")
    def cancel_batch(batch_id: str) -> dict[str, Any]:
        repo, supervisor = services()
        count = 0
        for j in repo.active_jobs():
            if j.get("batch_id") == batch_id:
                count += supervisor.cancel_job(j["job_id"])
        return {"cancelled_attempts": count}
