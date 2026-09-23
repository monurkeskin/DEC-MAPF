"""One lazy, synchronized owner for the workspace's processes and coordinators."""

from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from mapf.application.experiments import ExperimentCoordinator, ExperimentService
from mapf.application.jobs import JobSupervisor
from mapf.application.resources import ResourcePolicy
from mapf.application.runs import RunRepository


class WorkspaceServices:
    """Lazily compose one repository, supervisor and experiment coordinator.

    The FastAPI lifespan closes these owned services, including exceptional
    exits. Route groups share this owner rather than creating worker pools.
    """

    def __init__(self, data_dir: str | Path | None) -> None:
        self.data_dir = data_dir
        self.lock = threading.Lock()
        self.repository: RunRepository | None = None
        self.supervisor: JobSupervisor | None = None
        self.coordinator: ExperimentCoordinator | None = None

    def services(self) -> tuple[RunRepository, JobSupervisor]:
        with self.lock:
            if self.repository is None:
                repository = RunRepository(self.data_dir or os.environ.get("MAPF_WORKSPACE_DIR", "data/workspace"))
                resource_path = os.environ.get("MAPF_RESOURCE_POLICY")
                policy = ResourcePolicy.model_validate_json(Path(resource_path).read_text()) if resource_path else None
                supervisor = JobSupervisor(repository, max_workers=int(os.environ.get("MAPF_WORKERS", "2")),
                                           resource_policy=policy)
                self.repository, self.supervisor = repository, supervisor
            assert self.supervisor is not None
            return self.repository, self.supervisor

    def experiments(self) -> ExperimentCoordinator:
        repository, supervisor = self.services()
        with self.lock:
            if self.coordinator is None:
                self.coordinator = ExperimentCoordinator(ExperimentService(repository), supervisor)
            return self.coordinator

    def close(self) -> None:
        if self.coordinator is not None:
            self.coordinator.close()
        if self.supervisor is not None:
            self.supervisor.close()

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> Any:
        try:
            yield
        finally:
            self.close()
