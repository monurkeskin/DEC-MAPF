"""HTTP routes for workspace scenarios; execution stays in application services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from mapf.application.contracts import (
    MovingAIImport,
    ScenarioValidateRequest,
    ScenarioValidateResponse,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.movingai import movingai_snapshot
from mapf.application.plans import (
    builtins,
    instance_from_snapshot,
    scenario_snapshot,
)
from mapf.application.responses import (
    ScenarioDetail,
    ScenarioSummary,
)
from mapf.application.runs import RunRepository
from mapf.application.scenarios import ScenarioService
from mapf.core.models import SimulationSetting


def register(
    api: APIRouter, services: Callable[[], tuple[RunRepository, JobSupervisor]]
) -> None:
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
        snap = movingai_snapshot(request)
        repo, _ = services()
        return dict(snap, scenario_id=repo.save_scenario(snap))
