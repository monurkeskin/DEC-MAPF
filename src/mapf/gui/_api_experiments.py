"""HTTP routes for workspace experiments; execution stays in application services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from mapf.application.analysis_exports import experiment_archive
from mapf.application.experiments import (
    ExperimentCoordinator,
    ExperimentSpec,
    compile_experiment,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.responses import (
    AnalysisRequest,
    AnalysisResponse,
    ExperimentStart,
)
from mapf.application.runs import RunRepository


def register(
    api: APIRouter,
    services: Callable[[], tuple[RunRepository, JobSupervisor]],
    experiments: Callable[[], ExperimentCoordinator],
) -> None:
    @api.post("/experiments/preview")
    def experiment_plan(request: ExperimentSpec) -> dict[str, Any]:
        return compile_experiment(request.model_dump(mode="json"), services()[0])

    @api.post("/experiments", status_code=202)
    def experiment_start(request: ExperimentStart) -> dict[str, Any]:
        return experiments().start(
            request.manifest, resume=request.resume, retry_failed=request.retry_failed
        )

    @api.get("/experiments")
    def experiment_list() -> list[dict[str, Any]]:
        return experiments().service.manifests()

    @api.get("/experiments/{experiment_id}")
    def experiment_status(experiment_id: str) -> dict[str, Any]:
        coordinator = experiments()
        return dict(
            coordinator.service.summary(experiment_id),
            driver_error=coordinator.error
            if coordinator.active == experiment_id
            else None,
        )

    @api.get("/experiments/{experiment_id}/rows")
    def experiment_rows(experiment_id: str) -> list[dict[str, Any]]:
        return experiments().service.rows(experiment_id)

    @api.get("/experiments/{experiment_id}/manifest")
    def experiment_manifest(experiment_id: str) -> dict[str, Any]:
        return experiments().service.get_manifest(experiment_id)

    @api.post("/experiments/{experiment_id}/stop")
    def experiment_stop(experiment_id: str) -> dict[str, str]:
        return experiments().stop(experiment_id)

    @api.post("/experiments/{experiment_id}/analysis", response_model=AnalysisResponse)
    def experiment_analysis(
        experiment_id: str, request: AnalysisRequest
    ) -> dict[str, Any]:
        from mapf.analytics.experiment import analyze_experiment

        return analyze_experiment(
            experiments().service.rows(experiment_id),
            request.left,
            request.right,
            filters=request.filters,
        )

    @api.post("/experiments/{experiment_id}/export")
    def experiment_export(experiment_id: str, request: AnalysisRequest) -> Response:
        content = experiment_archive(experiments().service, experiment_id, request)
        return Response(
            content,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="experiment-analysis.zip"'
            },
        )
