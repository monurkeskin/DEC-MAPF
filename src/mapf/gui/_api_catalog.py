"""HTTP routes for workspace catalog; execution stays in application services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter

from mapf.application.artifacts import (
    METRICS,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.presets import PresetDescriptor, get_preset
from mapf.application.runs import RunRepository
from mapf.application.solvers import SolverCapability, SolverRegistry


def register(
    api: APIRouter, services: Callable[[], tuple[RunRepository, JobSupervisor]]
) -> None:
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
            "resource_policy": supervisor.resource_policy.model_dump()
            if supervisor.resource_policy
            else None,
            "resource_status": supervisor.admission.latest
            if supervisor.admission
            else None,
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

        return {
            **preview_profile(profile_id),
            "max_concurrency": services()[1].max_workers,
        }

    @api.get("/metrics")
    def metrics() -> dict[str, Any]:
        return {"version": "delivered-metrics-v2", "metrics": METRICS}
