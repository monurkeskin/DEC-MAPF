"""FastAPI application for MAPF Researcher Studio Dashboard.

Exposes REST and SSE endpoints for single and comparative simulation playback,
batch benchmark execution, LaTeX table export, and archived dataset browsing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import polars as pl
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import (
    JSONResponse,
    StreamingResponse,
)

from mapf.application.experiments import ExperimentCoordinator, ExperimentService
from mapf.application.jobs import JobSupervisor
from mapf.application.runs import RunRepository
from mapf.core.models import (
    SimulationSetting,
)
from mapf.core.movingai import generate_benchmark_map, generate_stern_scenario
from mapf.gui.batch_manager import benchmark_manager
from mapf.gui.schemas import (
    BatchBenchmarkRequest,
    Point2D,
    SimulationRequest,
    SimulationResponse,
    SolverRunResult,
)
from mapf.solvers.base import MAPFInstance


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    import os
    import threading
    from contextlib import asynccontextmanager

    from mapf.application.resources import ResourcePolicy
    from mapf.gui.api_v1 import router
    from mapf.gui.assets import mount_workspace

    composition_lock = threading.Lock()
    state: dict[str, Any] = {}

    def services() -> tuple[RunRepository, JobSupervisor]:
        with composition_lock:
            if "repository" not in state:
                repo = RunRepository(
                    data_dir or os.environ.get("MAPF_WORKSPACE_DIR", "data/workspace")
                )
                resource_path = os.environ.get("MAPF_RESOURCE_POLICY")
                policy = ResourcePolicy.model_validate_json(Path(resource_path).read_text()) if resource_path else None
                supervisor = JobSupervisor(repo, max_workers=int(os.environ.get("MAPF_WORKERS", "2")),
                                           resource_policy=policy)
                state.update(repository=repo, supervisor=supervisor)
            return state["repository"], state["supervisor"]

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        yield
        if "experiments" in state:
            state["experiments"].close()
        if "supervisor" in state:
            state["supervisor"].close()

    def experiments() -> ExperimentCoordinator:
        repo, supervisor = services()
        with composition_lock:
            if "experiments" not in state:
                state["experiments"] = ExperimentCoordinator(ExperimentService(repo), supervisor)
            return cast(ExperimentCoordinator, state["experiments"])

    app = FastAPI(
        lifespan=lifespan,
        title="DEC-MAPF - Research Workspace",
        description="Decentralized MAPF simulation and centralized solver comparisons, independent trajectory validation, replay and experiment analysis.",
        version="0.1.0a1",
    )

    dist_dir = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    static_dir = Path(__file__).parent / "static"
    app.state.workspace_services = services
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def local_limits(request: Request, call_next: Any) -> Any:
        from urllib.parse import urlparse

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).hostname not in {
                "localhost",
                "127.0.0.1",
                "::1",
                "testserver",
            }:
                return JSONResponse(
                    {"detail": "This workspace accepts local browser origins only"},
                    status_code=403,
                )
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 16 * 1024 * 1024:
                    return JSONResponse(
                        {"detail": "Request exceeds 16 MiB local import limit"},
                        status_code=413,
                    )
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid_input(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            {"detail": str(exc), "kind": "invalid_input_or_artifact"}, status_code=422
        )

    @app.exception_handler(KeyError)
    async def missing_resource(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"detail": f"Resource not found: {exc}"}, status_code=404)

    @app.exception_handler(OverflowError)
    async def capacity(request: Request, exc: OverflowError) -> JSONResponse:
        return JSONResponse(
            {"detail": str(exc), "kind": "local_capacity"}, status_code=429
        )

    @app.exception_handler(OSError)
    async def storage_error(request: Request, exc: OSError) -> JSONResponse:
        return JSONResponse(
            {"detail": str(exc), "kind": "storage_failure"}, status_code=507
        )

    app.include_router(router(services, experiments))

    mount_workspace(app, dist_dir, static_dir)

    @app.get("/api/presets")
    async def get_presets() -> list[dict[str, Any]]:
        """Preset academic scenarios directly replicating JAAMAS 2024 experiment anchors."""
        return [
            {
                "id": "preset_empty_32_s2_fov5",
                "name": "Appendix A: empty-32-32 Setting 2 (FoV 5, k=80) [historical configuration; results unqualified]",
                "grid_width": 32,
                "grid_height": 32,
                "agent_count": 80,
                "solver": "HeatMap",
                "compare_solver": "PathAware",
                "commitment_type": "ZC",
                "compare_commitment_type": "ZC",
                "fov_size": 5,
                "obstacle_density": 0.0,
                "setting": 2,
                "random_seed": 42,
            },
            {
                "id": "preset_random_32_10_s4_fov7",
                "name": "Appendix A: random-32-32-10 Setting 4 (FoV 7, k=80) [historical configuration; results unqualified]",
                "grid_width": 32,
                "grid_height": 32,
                "agent_count": 80,
                "solver": "HeatMap",
                "compare_solver": "PathAware",
                "commitment_type": "ZC",
                "compare_commitment_type": "ZC",
                "fov_size": 7,
                "obstacle_density": 0.10,
                "setting": 4,
                "random_seed": 101,
            },
            {
                "id": "preset_commitment_s4_sc_vs_zc",
                "name": "Section 5.4: SC vs. ZC Commitment Comparison (Setting 4, k=80)",
                "grid_width": 16,
                "grid_height": 16,
                "agent_count": 80,
                "solver": "HeatMap",
                "compare_solver": "HeatMap",
                "commitment_type": "SC",
                "compare_commitment_type": "ZC",
                "fov_size": 5,
                "obstacle_density": 0.0,
                "setting": 4,
                "random_seed": 42,
            },
            {
                "id": "preset_dense_scaling_k80",
                "name": "Main Benchmark: 16x16 Setting 4 High Density (k=80, FoV 5)",
                "grid_width": 16,
                "grid_height": 16,
                "agent_count": 80,
                "solver": "HeatMap",
                "compare_solver": "PathAware",
                "commitment_type": "SC",
                "compare_commitment_type": "SC",
                "fov_size": 5,
                "obstacle_density": 0.0,
                "setting": 4,
                "random_seed": 137,
            },
        ]

    @app.post("/api/simulate", response_model=SimulationResponse)
    async def run_simulation(req: SimulationRequest) -> SimulationResponse:

        # 1. Generate a local synthetic map (not an archived MovingAI instance)
        obstacles = generate_benchmark_map(
            width=req.grid_width,
            height=req.grid_height,
            obstacle_density=req.obstacle_density,
            seed=req.random_seed,
        )

        # 2. Generate connected local scenarios with explicit distance bounds
        min_d = 2 if req.grid_width <= 16 else 4
        max_d = 12 if req.grid_width <= 16 else 24
        try:
            pairs = generate_stern_scenario(
                width=req.grid_width,
                height=req.grid_height,
                obstacles=obstacles,
                num_agents=req.agent_count,
                min_dist=min_d,
                max_dist=max_d,
                seed=req.random_seed,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        starts = [p[0] for p in pairs]
        goals = [p[1] for p in pairs]

        starts_map = {f"Agent_{i + 1:02d}": starts[i] for i in range(req.agent_count)}
        goals_map = {f"Agent_{i + 1:02d}": goals[i] for i in range(req.agent_count)}

        instance = MAPFInstance(
            starts=starts_map,
            goals=goals_map,
            grid_width=req.grid_width,
            grid_height=req.grid_height,
            obstacles=obstacles,
        )

        setting_enum = SimulationSetting(req.setting)
        async def owned_result(name: str, commitment: str) -> SolverRunResult:
            from mapf.application.contracts import JobSubmissionRequest
            from mapf.application.runs import TERMINAL

            solver_id = "EECBS" if name.startswith("EECBS-") else name
            submission = JobSubmissionRequest.model_validate({
                "grid_width": instance.grid_width, "grid_height": instance.grid_height,
                "starts": {a: (p.x, p.y) for a, p in instance.starts.items()},
                "goals": {a: (p.x, p.y) for a, p in instance.goals.items()},
                "obstacles": [(p.x, p.y) for p in instance.obstacles],
                "solver_id": solver_id, "setting": setting_enum.name,
                "commitment_type": commitment, "fov_size": req.fov_size,
                "initial_tokens": req.initial_tokens, "max_steps": req.max_steps,
                "timeout_sec": req.timeout_sec, "random_seed": req.random_seed,
                "suboptimality": float(name.split("-")[1]) if name.startswith("EECBS-") else 1.1,
            })
            repo, supervisor = services()
            job = supervisor.submit(submission)
            try:
                while True:
                    status = repo.get_job(job["job_id"])
                    assert status is not None
                    if status["state"] == "completed":
                        payload = repo.get_run(job["run_id"])
                        assert payload is not None
                        result = SolverRunResult.model_validate(payload["result"])
                        result.solver_key = name  # only the deprecated facade's display identifier
                        return result
                    if status["state"] in TERMINAL:
                        raise HTTPException(408 if status["state"] == "timed_out" else 500,
                                            detail={"job_id": job["job_id"], "state": status["state"], "error": status["error"]})
                    await asyncio.sleep(.05)
            except asyncio.CancelledError:
                supervisor.cancel_job(job["job_id"])
                raise

        primary_res = await owned_result(req.solver, req.commitment_type)
        comparison_res = (await owned_result(req.compare_solver, req.compare_commitment_type or req.commitment_type)
                          if req.compare_solver else None)
        inst_hash, run_id = primary_res.instance_hash, primary_res.run_id

        return SimulationResponse(
            instance_hash=inst_hash,
            run_id=run_id,
            random_seed=req.random_seed,
            grid_width=req.grid_width,
            grid_height=req.grid_height,
            setting=req.setting,
            disappear_at_target=setting_enum.disappear_at_target,
            obstacles=[Point2D(x=p.x, y=p.y) for p in obstacles],
            starts=[Point2D(x=p.x, y=p.y) for p in starts],
            goals=[Point2D(x=p.x, y=p.y) for p in goals],
            primary=primary_res,
            comparison=comparison_res,
            solver=primary_res.solver,
            is_centralized=primary_res.is_centralized,
            status=primary_res.status,
            success=primary_res.success,
            solved_count=primary_res.solved_count,
            total_agents=req.agent_count,
            total_steps=primary_res.makespan,
            makespan=primary_res.makespan,
            runtime_ms=primary_res.runtime_ms,
            negotiation_count=primary_res.negotiation_count,
            successful_negotiations=primary_res.successful_negotiations,
            information_sharing_rate=primary_res.information_sharing_rate,
            norm_path_diff=primary_res.norm_path_diff,
            paths=primary_res.paths,
            frames=primary_res.frames,
        )

    # Batch Benchmark Endpoints
    @app.post("/api/benchmark/start")
    async def start_benchmark(req: BatchBenchmarkRequest) -> dict[str, Any]:
        raise HTTPException(410, "Legacy benchmark launch is retired. Preview and run an explicit budgeted /api/v1/experiments manifest, or use mapf batch.")

    @app.post("/api/benchmark/cancel/{task_id}")
    async def cancel_benchmark(task_id: str) -> dict[str, Any]:
        success = benchmark_manager.cancel_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"task_id": task_id, "status": "CANCELLED"}

    @app.get("/api/benchmark/status/{task_id}")
    async def get_benchmark_status(task_id: str) -> dict[str, Any]:
        task = benchmark_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Benchmark task not found")
        return {
            "task_id": task.task_id,
            "suite_name": task.suite_name,
            "total_runs": task.total_runs,
            "completed_runs": task.completed_runs,
            "elapsed_sec": round(task.elapsed_sec, 1),
            "status": task.status,
            "current_run_info": task.current_run_info,
            "results_count": len(task.results),
            "error": task.error_message,
        }

    @app.get("/api/benchmark/stream/{task_id}")
    async def stream_benchmark_events(
        task_id: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
        cursor: int | None = Query(default=None),
    ) -> StreamingResponse:
        """SSE stream endpoint supporting Last-Event-ID header and cursor query."""
        task = benchmark_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Benchmark task not found")

        # Prioritize Last-Event-ID header, fallback to cursor query parameter
        resolved_cursor: int | None = None
        if last_event_id:
            try:
                resolved_cursor = int(last_event_id)
            except ValueError:
                resolved_cursor = None
        elif cursor is not None:
            resolved_cursor = cursor

        return StreamingResponse(
            benchmark_manager.stream_task_events(
                task_id, last_event_id=resolved_cursor
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/benchmark/tasks")
    async def list_benchmark_tasks() -> list[dict[str, Any]]:
        return benchmark_manager.list_tasks()

    @app.get("/api/results/{suite_name}")
    async def get_archived_results(suite_name: str) -> dict[str, Any]:
        root = Path(__file__).resolve().parent.parent.parent.parent
        res_dir = root / "benchmarks" / "results"
        file_map = {
            "appendix_32x32": res_dir / "appendix_32x32_results.parquet",
            "commitment_types": res_dir / "commitment_types_results.parquet",
            "main_matrix": res_dir / "precise_statistical_audit.parquet",
            "regression_core": res_dir
            / "regression"
            / "regression_core_results.parquet",
        }
        target_file = file_map.get(suite_name)
        if not target_file or not target_file.exists():
            raise HTTPException(
                status_code=404, detail=f"Archived dataset {suite_name} not found"
            )

        df = pl.read_parquet(target_file)
        return {
            "suite_name": suite_name,
            "total_rows": len(df),
            "records": df.to_dicts(),
        }

    @app.get("/api/export/latex/{suite_name}")
    async def export_latex_table(suite_name: str) -> dict[str, str]:
        root = Path(__file__).resolve().parent.parent.parent.parent
        res_dir = root / "benchmarks" / "results"

        if suite_name == "appendix_32x32":
            p = res_dir / "appendix_32x32_results.parquet"
            if not p.exists():
                raise HTTPException(status_code=404, detail="Dataset not ready")
            df = pl.read_parquet(p)
            summary = (
                df.group_by(["map_name", "setting_name", "fov"])
                .agg(pl.col("success").mean())
                .sort(["map_name", "setting_name", "fov"])
            )
            latex_lines = [
                r"\begin{table}[t]",
                r"\centering",
                r"\caption{JAAMAS 2024 Appendix A: $32 \times 32$ Map Success Rates ($k=80$)}",
                r"\begin{tabular}{lllrr}",
                r"\toprule",
                r"Map & Setting & FoV & Solution Rate (\%) \\",
                r"\midrule",
            ]
            for row in summary.iter_rows(named=True):
                m_name = str(row["map_name"]).replace("_", r"\_")
                s_name = str(row["setting_name"]).replace("_", r"\_")
                latex_lines.append(
                    f"{m_name} & {s_name} & {row['fov']} & {row['success'] * 100:.1f}\\% \\\\"
                )
            latex_lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
            return {"latex": "\n".join(latex_lines)}

        elif suite_name == "commitment_types":
            p = res_dir / "commitment_types_results.parquet"
            if not p.exists():
                raise HTTPException(status_code=404, detail="Dataset not ready")
            df = pl.read_parquet(p)
            summary = (
                df.group_by(["setting_name", "commitment", "fov"])
                .agg(
                    [
                        pl.col("success").mean(),
                        pl.col("norm_path_diff").mean(),
                        pl.col("negotiations").mean(),
                    ]
                )
                .sort(["setting_name", "commitment", "fov"])
            )
            latex_lines = [
                r"\begin{table}[t]",
                r"\centering",
                r"\caption{Section 5.4 Commitment Protocol Comparison ($k=80$)}",
                r"\begin{tabular}{lllrrr}",
                r"\toprule",
                r"Setting & Protocol & FoV & Success (\%) & Path Diff (\%) & Negotiations \\",
                r"\midrule",
            ]
            for row in summary.iter_rows(named=True):
                s_name = str(row["setting_name"]).replace("_", r"\_")
                comm_name = str(row["commitment"]).replace("_", r"\_")
                latex_lines.append(
                    f"{s_name} & {comm_name} & {row['fov']} & {row['success'] * 100:.1f}\\% & {row['norm_path_diff']:.2f}\\% & {row['negotiations']:.1f} \\\\"
                )
            latex_lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
            return {"latex": "\n".join(latex_lines)}

        return {"latex": "% No LaTeX template available for this suite"}

    return app


app = create_app()
