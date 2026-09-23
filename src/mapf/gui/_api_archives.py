"""HTTP routes for workspace archives; execution stays in application services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from mapf.application.jobs import JobSupervisor
from mapf.application.legacy import quarantine_text
from mapf.application.runs import RunRepository


class LegacyArchiveRequest(BaseModel):
    name: str = Field(max_length=160)
    content: str = Field(max_length=1000000)


def register(
    api: APIRouter, services: Callable[[], tuple[RunRepository, JobSupervisor]]
) -> None:
    @api.post("/archives/quarantine", status_code=201)
    def legacy_archive(request: LegacyArchiveRequest) -> dict[str, Any]:
        return quarantine_text(services()[0], request.name, request.content)
