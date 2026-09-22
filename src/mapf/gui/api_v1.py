"""Thin HTTP adapter for the locally owned research workspace."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from mapf.application.artifacts import (
    METRICS,
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
    JobEvent,
    JobStatusResponse,
    JobSubmissionRequest,
    MovingAIImport,
    PlanAdmission,
    PlanRequest,
    ScenarioValidateRequest,
    ScenarioValidateResponse,
)
from mapf.application.experiments import (
    ExperimentCoordinator,
    ExperimentSpec,
    compile_experiment,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.library import RunLibrary
from mapf.application.plans import (
    builtins,
    instance_from_snapshot,
    preview_batch,
    scenario_snapshot,
)
from mapf.application.presets import PresetDescriptor, get_preset
from mapf.application.responses import (
    AnalysisRequest,
    AnalysisResponse,
    ExperimentStart,
    FrameSlice,
    PlanResponse,
    RunDetail,
    RunPage,
    RunSummary,
    ScenarioDetail,
    ScenarioSummary,
)
from mapf.application.runs import TERMINAL, RunRepository, atomic_write
from mapf.application.scenarios import ScenarioService
from mapf.application.solvers import SolverCapability, SolverRegistry
from mapf.core.models import SimulationSetting
from mapf.telemetry.schema import TelemetryEnvelope


class LegacyArchiveRequest(BaseModel):
    name: str = Field(max_length=160)
    content: str = Field(max_length=1000000)


def router(services: Callable[[], tuple[RunRepository, JobSupervisor]],
           experiments: Callable[[], ExperimentCoordinator]) -> APIRouter:
    api = APIRouter(prefix="/api/v1")

    @api.get("/health")
    def health() -> dict[str, Any]:
        repo, supervisor = services()
        return {
            "status": "degraded" if hasattr(supervisor, "last_error") else "ok",
            "schema_version": "1.0",
            "worker_limit": supervisor.max_workers,
            "queue_limit": supervisor.max_pending,
            "used_bytes": repo.usage_bytes(),
            "quota_bytes": repo.quota_bytes,
            "error": getattr(supervisor, "last_error", None),
            "resource_policy": supervisor.resource_policy.model_dump() if supervisor.resource_policy else None,
            "resource_status": supervisor.admission.latest if supervisor.admission else None,
        }

    @api.get("/capabilities", response_model=list[SolverCapability])
    def capabilities() -> list[dict[str, Any]]:
        return [asdict(c) for c in SolverRegistry.list_capabilities()]

    @api.get("/profiles")
    def profiles() -> list[dict[str, Any]]:
        from mapf.application.profiles import list_profiles

        return list_profiles()

    @api.get("/presets/{preset_id}", response_model=PresetDescriptor)
    def preset(preset_id: str) -> PresetDescriptor:
        return get_preset(preset_id)

    @api.get("/profiles/{profile_id}")
    def profile(profile_id: str) -> dict[str, Any]:
        from mapf.application.profiles import preview_profile

        return {**preview_profile(profile_id), "max_concurrency": services()[1].max_workers}

    @api.get("/runs/{run_id}/telemetry", response_model=TelemetryEnvelope)
    def telemetry(run_id: str) -> dict[str, Any]:
        payload = services()[0].get_run(run_id, include_frames=False)
        if payload is None:
            raise KeyError(run_id)
        records = payload["result"].get("telemetry_events", [])
        if any(e.get("schema_version") != "telemetry-2" for e in records):
            raise ValueError("Legacy events have no qualified telemetry-2 schema; use archived run export")
        return {"schema_version": "telemetry-2", "events": records}

    @api.get("/metrics")
    def metrics() -> dict[str, Any]:
        return {"version": "delivered-metrics-v2", "metrics": METRICS}

    @api.get("/scenarios", response_model=list[ScenarioSummary])
    def scenarios() -> list[dict[str, Any]]:
        repo, _ = services()
        result = [asdict(s) for s in ScenarioService.get_built_in_scenarios()]
        for snap in repo.list_scenarios():
            result.append(
                dict(
                    snap,
                    agent_count=len(snap["starts"]),
                    obstacle_count=len(snap["obstacles"]),
                    density=len(snap["obstacles"])
                    / (snap["grid_width"] * snap["grid_height"]),
                    description="Saved immutable scenario",
                )
            )
        return result

    @api.get("/scenarios/{scenario_id}", response_model=ScenarioDetail)
    def scenario(scenario_id: str) -> dict[str, Any]:
        repo, _ = services()
        result = builtins().get(scenario_id)
        if result is None:
            result = repo.get_scenario(scenario_id)
        if result is None:
            raise KeyError(scenario_id)
        return result

    @api.post("/scenarios/validate", response_model=ScenarioValidateResponse)
    def validate(request: ScenarioValidateRequest) -> ScenarioValidateResponse:
        inst = instance_from_snapshot(request.model_dump(mode="json"))
        errors = ScenarioService.validate_instance(
            inst, SimulationSetting[request.setting]
        )
        return ScenarioValidateResponse(is_valid=not errors, errors=errors)

    @api.post("/scenarios", status_code=201)
    def save_scenario(request: ScenarioValidateRequest) -> dict[str, Any]:
        repo, _ = services()
        snap = scenario_snapshot(request)
        sid = repo.save_scenario(snap)
        return dict(snap, scenario_id=sid)

    @api.post("/scenarios/import-movingai", status_code=201)
    def movingai(request: MovingAIImport) -> dict[str, Any]:
        import hashlib

        # Strictly validate text dimensions before using legacy parser semantics.
        lines = request.map_text.strip().splitlines()
        if (
            len(lines) < 5
            or lines[0].strip() != "type octile"
            or lines[3].strip() != "map"
        ):
            raise ValueError("Expected MovingAI octile map header")
        h, w = int(lines[1].split()[1]), int(lines[2].split()[1])
        if (
            not (1 <= w <= 64 and 1 <= h <= 64)
            or len(lines[4:]) != h
            or any(len(row) != w for row in lines[4:])
        ):
            raise ValueError(
                "MovingAI map dimensions do not match its rows or exceed supported limits"
            )
        if any(c not in ".G@OTSW" for row in lines[4:] for c in row):
            raise ValueError("Unsupported MovingAI terrain character")
        rows = request.scenario_text.strip().splitlines()
        if not rows or rows[0].strip() != "version 1":
            raise ValueError("Expected MovingAI scenario version 1")
        pairs = []
        map_names = set()
        for row in rows[1:]:
            f = row.split()
            if len(f) != 9 or int(f[2]) != w or int(f[3]) != h:
                raise ValueError(
                    "Scenario row is malformed or references incompatible dimensions"
                )
            map_names.add(f[1])
            pairs.append(((int(f[4]), int(f[5])), (int(f[6]), int(f[7]))))
        if len(map_names) != 1 or len(pairs) < request.agent_count:
            raise ValueError("Select enough agents from one map reference")
        pairs = pairs[: request.agent_count]
        snap = scenario_snapshot(
            ScenarioValidateRequest(
                grid_width=w,
                grid_height=h,
                setting=request.setting,
                name=request.name,
                starts={f"agent_{i}": a for i, (a, _) in enumerate(pairs)},
                goals={f"agent_{i}": b for i, (_, b) in enumerate(pairs)},
                obstacles=[
                    (x, y)
                    for y, row in enumerate(lines[4:])
                    for x, c in enumerate(row)
                    if c in "@OTW"
                ],
            )
        )
        snap["source"] = {
            "format": "MovingAI",
            "map_sha256": hashlib.sha256(request.map_text.encode()).hexdigest(),
            "scenario_sha256": hashlib.sha256(
                request.scenario_text.encode()
            ).hexdigest(),
            "selection": f"first {request.agent_count} rows; no random subsample",
        }
        repo, _ = services()
        return dict(snap, scenario_id=repo.save_scenario(snap))

    @api.post("/plans/preview", response_model=PlanResponse)
    def plan(request: PlanRequest) -> dict[str, Any]:
        repo, supervisor = services()
        return {**preview_batch(request.jobs, repo), "max_concurrency": supervisor.max_workers}

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

    @api.post("/experiments/preview")
    def experiment_plan(request: ExperimentSpec) -> dict[str, Any]:
        return compile_experiment(request.model_dump(mode="json"), services()[0])

    @api.post("/experiments", status_code=202)
    def experiment_start(request: ExperimentStart) -> dict[str, Any]:
        return experiments().start(request.manifest, resume=request.resume, retry_failed=request.retry_failed)

    @api.get("/experiments")
    def experiment_list() -> list[dict[str, Any]]:
        return experiments().service.manifests()

    @api.get("/experiments/{experiment_id}")
    def experiment_status(experiment_id: str) -> dict[str, Any]:
        coordinator = experiments()
        return dict(coordinator.service.summary(experiment_id),
                    driver_error=coordinator.error if coordinator.active == experiment_id else None)

    @api.get("/experiments/{experiment_id}/rows")
    def experiment_rows(experiment_id: str) -> list[dict[str, Any]]:
        return experiments().service.rows(experiment_id)

    @api.get("/experiments/{experiment_id}/manifest")
    def experiment_manifest(experiment_id: str) -> dict[str, Any]:
        return experiments().service.get_manifest(experiment_id)

    @api.post("/experiments/{experiment_id}/stop")
    def experiment_stop(experiment_id: str) -> dict[str, str]:
        driver = experiments()
        if driver.active != experiment_id:
            raise ValueError("This experiment is not active")
        driver.close()
        return {"state": "interrupted", "experiment_id": experiment_id}

    @api.post("/experiments/{experiment_id}/analysis", response_model=AnalysisResponse)
    def experiment_analysis(experiment_id: str, request: AnalysisRequest) -> dict[str, Any]:
        from mapf.analytics.experiment import analyze_experiment
        return analyze_experiment(experiments().service.rows(experiment_id), request.left, request.right,
                                  filters=request.filters)

    @api.post("/experiments/{experiment_id}/export")
    def experiment_export(experiment_id: str, request: AnalysisRequest) -> Response:
        import io
        import tempfile
        import zipfile
        from pathlib import Path

        from mapf.analytics.experiment import analyze_experiment, export_analysis
        rows = experiments().service.rows(experiment_id)
        result = analyze_experiment(rows, request.left, request.right, filters=request.filters)
        if request.expected_cohort_sha256 and request.expected_cohort_sha256 != result["cohort_sha256"]:
            raise ValueError("Experiment outcomes changed; analyze again before exporting")
        buffer = io.BytesIO()
        with tempfile.TemporaryDirectory(prefix="mapf-analysis-") as directory:
            from mapf.application.runs import encode
            folder = Path(directory)
            (folder / "experiment-manifest.json").write_bytes(encode(experiments().service.get_manifest(experiment_id)))
            (folder / "all-planned-trials.json").write_bytes(encode(rows))
            export_analysis(result, folder)
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(Path(directory).iterdir()):
                    archive.write(file, file.name)
        return Response(buffer.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="experiment-analysis.zip"'})

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
        if last_event_id is not None:
            try:
                cursor = int(last_event_id)
            except ValueError as exc:
                raise HTTPException(
                    422, "Last-Event-ID must be a nonnegative integer"
                ) from exc
            if cursor < 0:
                raise HTTPException(422, "Last-Event-ID must be nonnegative")
        all_events = repo.events(job_id)
        if cursor > len(all_events):
            raise HTTPException(
                409, "Cursor is ahead of journal; reload authoritative state"
            )

        async def events() -> Any:
            position = cursor
            heartbeat_at = asyncio.get_running_loop().time()
            while not await request.is_disconnected():
                for event in repo.events(job_id, position):
                    position = event["sequence"]
                    yield f"id: {position}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
                current = repo.get_job(job_id)
                if (
                    current
                    and current["state"] in TERMINAL
                    and not repo.events(job_id, position)
                ):
                    break
                now = asyncio.get_running_loop().time()
                if now - heartbeat_at >= 5:
                    yield ": heartbeat\n\n"
                    heartbeat_at = now
                await asyncio.sleep(0.1)

        return StreamingResponse(
            events(),
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
        for j in repo.list_jobs():
            if j.get("batch_id") == batch_id:
                count += supervisor.cancel_job(j["job_id"])
        return {"cancelled_attempts": count}

    @api.get("/runs", response_model=list[RunSummary])
    def runs(limit: int = Query(default=50, ge=1, le=100)) -> list[dict[str, Any]]:
        return services()[0].list_runs(limit)

    @api.get("/runs/page", response_model=RunPage)
    def run_page(limit: int = Query(default=50, ge=1, le=100),
                 cursor: str | None = Query(default=None, max_length=1024),
                 solver_name: str | None = Query(default=None, max_length=160),
                 validation_status: str | None = Query(default=None, max_length=160),
                 experiment_id: str | None = Query(default=None, max_length=160)) -> dict[str, Any]:
        return RunLibrary(services()[0]).page(limit=limit, cursor=cursor,
            solver_name=solver_name, validation_status=validation_status, experiment_id=experiment_id)

    @api.get("/runs/{run_id}", response_model=RunDetail, response_model_exclude_unset=True)
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

    @api.post("/archives/quarantine", status_code=201)
    def legacy_archive(request: LegacyArchiveRequest) -> dict[str, Any]:
        # Preserve source bytes; do not invent provenance or insert unverifiable results into cohorts.
        import hashlib

        repo, _ = services()
        raw = request.content.encode()
        sha = hashlib.sha256(raw).hexdigest()
        repo.ensure_space(len(raw) + 1000)
        archive_dir = repo.base_dir / "legacy"
        archive_dir.mkdir(exist_ok=True)
        atomic_write(archive_dir / f"{sha}.txt", raw)
        return {
            "sha256": sha,
            "bytes": len(raw),
            "name": request.name,
            "status": "quarantined",
            "missing": [
                "verified instance identity",
                "effective config",
                "code revision",
                "independent validation",
            ],
        }

    return api
