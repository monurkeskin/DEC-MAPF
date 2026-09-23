"""HTTP routes for workspace runs; execution stays in application services."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import Response

from mapf.application.artifacts import (
    export_bundle,
    import_bundle,
    latex_table,
    metrics_csv,
    standalone_html,
    svg_snapshot,
)
from mapf.application.comparison import compare_runs
from mapf.application.contracts import (
    ComparisonRequest,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.library import RunLibrary
from mapf.application.responses import (
    FrameSlice,
    RunDetail,
    RunPage,
    RunSummary,
)
from mapf.application.runs import RunRepository
from mapf.telemetry.schema import TelemetryEnvelope


def register(
    api: APIRouter, services: Callable[[], tuple[RunRepository, JobSupervisor]]
) -> None:
    @api.get("/runs/{run_id}/telemetry", response_model=TelemetryEnvelope)
    def telemetry(run_id: str) -> dict[str, Any]:
        payload = services()[0].get_run(run_id, include_frames=False)
        if payload is None:
            raise KeyError(run_id)
        records = payload["result"].get("telemetry_events", [])
        if any(e.get("schema_version") != "telemetry-2" for e in records):
            raise ValueError(
                "Legacy events have no qualified telemetry-2 schema; use archived run export"
            )
        return {"schema_version": "telemetry-2", "events": records}

    @api.get("/runs", response_model=list[RunSummary])
    def runs(limit: int = Query(default=50, ge=1, le=100)) -> list[dict[str, Any]]:
        return services()[0].list_runs(limit)

    @api.get("/runs/page", response_model=RunPage)
    def run_page(
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=1024),
        solver_name: str | None = Query(default=None, max_length=160),
        validation_status: str | None = Query(default=None, max_length=160),
        experiment_id: str | None = Query(default=None, max_length=160),
    ) -> dict[str, Any]:
        return RunLibrary(services()[0]).page(
            limit=limit,
            cursor=cursor,
            solver_name=solver_name,
            validation_status=validation_status,
            experiment_id=experiment_id,
        )

    @api.get(
        "/runs/{run_id}", response_model=RunDetail, response_model_exclude_unset=True
    )
    def run(run_id: str, include_frames: bool = True) -> dict[str, Any]:
        result = services()[0].get_run(run_id, include_frames=include_frames)
        if result is None:
            raise KeyError(run_id)
        return result

    @api.get("/runs/{run_id}/frames", response_model=FrameSlice)
    def frames(
        run_id: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, Any]:
        return services()[0].frame_slice(run_id, offset, limit)

    @api.get("/runs/{run_id}/export/{kind}")
    def export(run_id: str, kind: str, tick: int = Query(default=0, ge=0)) -> Response:
        payload = run(run_id)
        formats: dict[str, tuple[Callable[[], str], str]] = {
            "json": (
                lambda: json.dumps(export_bundle(payload), ensure_ascii=False),
                "application/json",
            ),
            "csv": (lambda: metrics_csv(payload), "text/csv"),
            "tex": (lambda: latex_table(payload), "text/plain"),
            "svg": (lambda: svg_snapshot(payload, tick), "image/svg+xml"),
            "html": (lambda: standalone_html(payload), "text/html"),
        }
        if kind not in formats:
            raise ValueError("Supported formats: json, csv, tex, svg, html")
        render, mime = formats[kind]
        return Response(
            render(),
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{run_id}.{kind}"'},
        )

    @api.post("/runs/import", status_code=201)
    def import_run(bundle: dict[str, Any]) -> dict[str, str]:
        try:
            return {"run_id": import_bundle(bundle, services()[0])}
        except (KeyError, TypeError, IndexError) as exc:
            raise ValueError("Malformed replay bundle") from exc

    @api.post("/runs/{run_id}/pin")
    def pin(run_id: str, pinned: bool = True) -> dict[str, Any]:
        services()[0].pin(run_id, pinned)
        return {"run_id": run_id, "pinned": pinned}

    @api.delete("/runs/{run_id}")
    def delete(run_id: str) -> dict[str, str]:
        services()[0].delete_run(run_id)
        return {"deleted": run_id}

    @api.post("/comparisons")
    def comparison(request: ComparisonRequest) -> dict[str, Any]:
        return compare_runs(
            services()[0], request.left, request.right, request.treatment_keys
        )
