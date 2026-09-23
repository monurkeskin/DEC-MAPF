"""Compatibility requests retain failure diagnostics and cancel only their job."""

import asyncio

import pytest
from fastapi import HTTPException

from mapf.gui import _legacy_simulation
from mapf.gui._legacy_simulation import LegacySimulation
from mapf.gui.schemas import SimulationRequest


class OwnedJob:
    def __init__(self, state):
        self.state = state
        self.cancelled = []

    def submit(self, request):
        return {"job_id": "job-owned", "run_id": "run-owned"}

    def get_job(self, job_id):
        assert job_id == "job-owned"
        return {"state": self.state, "error": "diagnostic witness"}

    def cancel_job(self, job_id):
        self.cancelled.append(job_id)


def simulation(owner):
    return LegacySimulation(SimulationRequest(grid_width=4, grid_height=4, agent_count=2),
                            lambda: (owner, owner))


@pytest.mark.parametrize(("state", "status"), [("timed_out", 408), ("failed", 500)])
def test_owned_terminal_failure_is_not_returned_as_a_success(state, status):
    owner = OwnedJob(state)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(simulation(owner).owned_result("CBS", "SC"))
    assert failure.value.status_code == status
    assert failure.value.detail == {"job_id": "job-owned", "state": state, "error": "diagnostic witness"}
    assert owner.cancelled == []


def test_disconnected_request_cancels_its_pending_job(monkeypatch):
    owner = OwnedJob("running")

    async def disconnect(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(_legacy_simulation.asyncio, "sleep", disconnect)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(simulation(owner).owned_result("CBS", "SC"))
    assert owner.cancelled == ["job-owned"]


def test_impossible_generated_scenario_returns_input_error_before_admission(monkeypatch):
    def unavailable(**kwargs):
        raise ValueError("Insufficient connected cells")

    monkeypatch.setattr(_legacy_simulation, "generate_stern_scenario", unavailable)
    with pytest.raises(HTTPException) as failure:
        simulation(OwnedJob("running"))
    assert failure.value.status_code == 400
    assert failure.value.detail == "Insufficient connected cells"
