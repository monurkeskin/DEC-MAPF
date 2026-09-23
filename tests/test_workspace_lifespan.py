"""Concurrent lazy initialization and shutdown must retain one process owner."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from mapf.application.jobs import JobSupervisor
from mapf.application.runs import RunRepository
from mapf.gui._services import WorkspaceServices


def test_concurrent_requests_share_one_supervisor_and_policy(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"max_cpu_percent": 75}))
    monkeypatch.setenv("MAPF_RESOURCE_POLICY", str(policy))
    monkeypatch.setenv("MAPF_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("MAPF_WORKERS", "1")
    owner = WorkspaceServices(None)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            services = list(pool.map(lambda _: owner.services(), range(8)))
            coordinators = list(pool.map(lambda _: owner.experiments(), range(8)))
        assert len({id(supervisor) for _, supervisor in services}) == 1
        assert len({id(coordinator) for coordinator in coordinators}) == 1
        assert services[0][1].max_workers == 1
        assert services[0][1].resource_policy.max_cpu_percent == 75
    finally:
        owner.close()


@pytest.mark.asyncio
async def test_lifespan_exception_still_releases_workspace_ownership(tmp_path):
    owner = WorkspaceServices(tmp_path)
    with pytest.raises(RuntimeError, match="application failed"):
        async with owner.lifespan(None):
            repository, supervisor = owner.services()
            raise RuntimeError("application failed")
    assert not supervisor._thread.is_alive()
    replacement = JobSupervisor(repository, max_workers=1)
    replacement.close()


def test_failed_initialization_is_retryable_without_partial_service_state(tmp_path, monkeypatch):
    owner = WorkspaceServices(tmp_path)
    monkeypatch.setenv("MAPF_WORKERS", "0")
    with pytest.raises(ValueError, match="worker count"):
        owner.services()
    assert owner.repository is None and owner.supervisor is None
    monkeypatch.setenv("MAPF_WORKERS", "1")
    repository, supervisor = owner.services()
    try:
        assert isinstance(repository, RunRepository)
        assert supervisor.max_workers == 1
    finally:
        owner.close()
