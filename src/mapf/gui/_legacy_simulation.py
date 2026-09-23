"""Deprecated single-run HTTP facade backed by the owned job supervisor."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from mapf.application.jobs import JobSupervisor
from mapf.application.runs import RunRepository
from mapf.core.models import SimulationSetting
from mapf.core.movingai import generate_benchmark_map, generate_stern_scenario
from mapf.gui.schemas import (
    Point2D,
    SimulationRequest,
    SimulationResponse,
    SolverRunResult,
)
from mapf.solvers.base import MAPFInstance

Services = Callable[[], tuple[RunRepository, JobSupervisor]]


class LegacySimulation:
    def __init__(self, request: SimulationRequest, services: Services) -> None:
        self.request = request
        self.services = services
        self.instance = self._generate_instance()

    def _generate_instance(self) -> MAPFInstance:
        # 1. Generate a local synthetic map (not an archived MovingAI instance)
        obstacles = generate_benchmark_map(
            width=self.request.grid_width,
            height=self.request.grid_height,
            obstacle_density=self.request.obstacle_density,
            seed=self.request.random_seed,
        )

        # 2. Generate connected local scenarios with explicit distance bounds
        min_d = 2 if self.request.grid_width <= 16 else 4
        max_d = 12 if self.request.grid_width <= 16 else 24
        try:
            pairs = generate_stern_scenario(
                width=self.request.grid_width,
                height=self.request.grid_height,
                obstacles=obstacles,
                num_agents=self.request.agent_count,
                min_dist=min_d,
                max_dist=max_d,
                seed=self.request.random_seed,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        starts = [p[0] for p in pairs]
        goals = [p[1] for p in pairs]

        starts_map = {f"Agent_{i + 1:02d}": starts[i] for i in range(self.request.agent_count)}
        goals_map = {f"Agent_{i + 1:02d}": goals[i] for i in range(self.request.agent_count)}

        return MAPFInstance(
            starts=starts_map,
            goals=goals_map,
            grid_width=self.request.grid_width,
            grid_height=self.request.grid_height,
            obstacles=obstacles,
        )


    async def owned_result(self, name: str, commitment: str) -> SolverRunResult:
        req, instance = self.request, self.instance
        setting_enum = SimulationSetting(req.setting)
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
        repo, supervisor = self.services()
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


    async def run(self) -> SimulationResponse:
        req = self.request
        setting_enum = SimulationSetting(req.setting)
        primary_res = await self.owned_result(req.solver, req.commitment_type)
        comparison_res = (await self.owned_result(req.compare_solver, req.compare_commitment_type or req.commitment_type)
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
            obstacles=[Point2D(x=p.x, y=p.y) for p in self.instance.obstacles],
            starts=[Point2D(x=p.x, y=p.y) for p in self.instance.starts.values()],
            goals=[Point2D(x=p.x, y=p.y) for p in self.instance.goals.values()],
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



def router(services: Services) -> APIRouter:
    api = APIRouter()

    @api.post("/api/simulate", response_model=SimulationResponse)
    async def run_simulation(req: SimulationRequest) -> SimulationResponse:
        return await LegacySimulation(req, services).run()

    return api
