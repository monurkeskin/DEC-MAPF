"""Catalog errors and idle SSE connections have explicit client-visible behavior."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from mapf.application.library import RunLibrary
from mapf.application.profiles import profile_jobs
from mapf.application.runs import RunRepository
from mapf.gui import _event_stream
from mapf.gui.app import create_app


def test_catalog_lists_only_runnable_profiles_as_enabled(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        profiles = client.get("/api/v1/profiles").json()
        enabled = {p["id"] for p in profiles if p["enabled"]}
        assert enabled == {"smoke-v1", "settings-smoke-v1"}
        result = client.get("/api/v1/profiles/settings-smoke-v1")
        assert result.status_code == 200
        assert {j["setting"] for j in result.json()["jobs"]} == {
            f"SETTING_{i}" for i in range(1, 5)
        }
        assert (
            client.get("/api/v1/metrics").json()["metrics"]["sum_of_costs"]["unit"]
            == "actions"
        )
    with pytest.raises(ValueError, match="unavailable"):
        profile_jobs("historical-jaamas-subsample")


@pytest.mark.parametrize(
    "kwargs", [{"limit": 0}, {"limit": 101}, {"solver_name": "a" * 161}]
)
def test_direct_library_call_enforces_the_same_bounds_as_http(tmp_path, kwargs):
    with pytest.raises(ValueError):
        RunLibrary(RunRepository(tmp_path)).page(**kwargs)


def test_negative_reconnect_cursor_is_a_client_error():
    with pytest.raises(HTTPException) as error:
        _event_stream.replay_cursor("-1", 0, 1)
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_idle_stream_sends_heartbeat_then_stops_on_disconnect(monkeypatch):
    times = iter([0.0, 5.0])
    monkeypatch.setattr(
        _event_stream.asyncio,
        "get_running_loop",
        lambda: SimpleNamespace(time=lambda: next(times)),
    )
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(_event_stream.asyncio, "sleep", sleep)
    calls = 0

    async def disconnected():
        nonlocal calls
        calls += 1
        return calls > 1

    repo = SimpleNamespace(
        events=lambda *args: [], get_job=lambda *_: {"state": "running"}
    )
    events = [
        event
        async for event in _event_stream.journal_events(
            repo, "job-test", SimpleNamespace(is_disconnected=disconnected), 0
        )
    ]
    assert events == [": heartbeat\n\n"]
    assert slept == [0.1]
