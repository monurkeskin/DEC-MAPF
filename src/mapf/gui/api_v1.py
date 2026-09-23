"""Compose independently testable HTTP route groups without constructing workers."""

from collections.abc import Callable

from fastapi import APIRouter

from mapf.application.experiments import ExperimentCoordinator
from mapf.application.jobs import JobSupervisor
from mapf.application.runs import RunRepository
from mapf.gui import (
    _api_archives,
    _api_catalog,
    _api_experiments,
    _api_jobs,
    _api_runs,
    _api_scenarios,
)
from mapf.gui._api_archives import LegacyArchiveRequest

__all__ = ["LegacyArchiveRequest", "router"]


def router(
    services: Callable[[], tuple[RunRepository, JobSupervisor]],
    experiments: Callable[[], ExperimentCoordinator],
) -> APIRouter:
    api = APIRouter(prefix="/api/v1")
    _api_catalog.register(api, services)
    _api_scenarios.register(api, services)
    _api_jobs.register(api, services)
    _api_experiments.register(api, services, experiments)
    _api_runs.register(api, services)
    _api_archives.register(api, services)
    return api
