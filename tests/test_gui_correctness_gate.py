"""Check replay timestamps, arrival states, validation and event reconnection."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from mapf.core.models import Path, Point, SimulationSetting
from mapf.gui.app import create_app
from mapf.gui.batch_manager import BenchmarkTaskManager
from mapf.gui.frame_builder import build_solver_run_result
from mapf.gui.schemas import SimulationResponse
from mapf.solvers.base import MAPFInstance, MAPFSolution


@pytest.fixture
def test_client(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        yield client


def test_t0_frame_contract_and_makespan_alignment():
    """Ensure frame 0 represents t=0 initial state, and frame count == makespan + 1."""
    starts = {"Agent_01": Point(0, 0), "Agent_02": Point(2, 0)}
    goals = {"Agent_01": Point(1, 0), "Agent_02": Point(2, 1)}
    instance = MAPFInstance(
        starts=starts,
        goals=goals,
        grid_width=4,
        grid_height=4,
        obstacles=set(),
    )

    # Agent 1 moves (0,0) -> (1,0) at t=1 (arrived)
    # Agent 2 moves (2,0) -> (2,0) at t=1, -> (2,1) at t=2 (arrived)
    solution = MAPFSolution(
        solver_name="TestSolver",
        is_centralized=False,
        success=True,
        paths={
            "Agent_01": Path(points=[Point(0, 0), Point(1, 0)]),
            "Agent_02": Path(points=[Point(2, 0), Point(2, 0), Point(2, 1)]),
        },
        makespan=2,
        sum_of_costs=3,
        runtime_ms=5.0,
    )

    res = build_solver_run_result(
        solver_name="TestSolver",
        solver_key="TestSolver",
        instance=instance,
        solution=solution,
        setting=SimulationSetting.SETTING_4,  # DaT = True
        fov_size=5,
    )

    # Frame count must be makespan + 1 (ticks: 0, 1, 2)
    assert len(res.frames) == 3
    assert res.frames[0].tick == 0
    assert res.frames[1].tick == 1
    assert res.frames[2].tick == 2

    # t=0: Agents must be strictly at starting positions
    assert res.frames[0].positions["Agent_01"] == [0, 0]
    assert res.frames[0].positions["Agent_02"] == [2, 0]
    assert res.frames[0].statuses["Agent_01"] == "active"
    assert res.frames[0].statuses["Agent_02"] == "active"

    # t=1: Agent 1 arrived at goal (Setting 4 DaT: reached at arrival tick)
    assert res.frames[1].positions["Agent_01"] == [1, 0]
    assert res.frames[1].statuses["Agent_01"] == "reached"
    assert res.frames[1].statuses["Agent_02"] == "active"

    # t=2: Agent 1 has disappeared under DaT; Agent 2 has reached goal
    assert res.frames[2].statuses["Agent_01"] == "disappeared"
    assert res.frames[2].statuses["Agent_02"] == "reached"


def test_agent_lifecycle_dat_vs_nodat():
    """Verify disappearance under DaT (Setting 4) vs permanent parked obstacle under noDaT (Setting 2)."""
    starts = {"Agent_01": Point(0, 0)}
    goals = {"Agent_01": Point(1, 0)}
    instance = MAPFInstance(
        starts=starts,
        goals=goals,
        grid_width=4,
        grid_height=4,
        obstacles=set(),
    )
    solution = MAPFSolution(
        solver_name="Test",
        is_centralized=False,
        success=True,
        paths={"Agent_01": Path(points=[Point(0, 0), Point(1, 0), Point(1, 0)])},
        makespan=2,
    )

    # 1. Under DaT (Setting 4)
    res_dat = build_solver_run_result(
        solver_name="Test",
        solver_key="Test",
        instance=instance,
        solution=solution,
        setting=SimulationSetting.SETTING_4,
        fov_size=5,
    )
    assert res_dat.frames[1].statuses["Agent_01"] == "reached"
    assert res_dat.frames[2].statuses["Agent_01"] == "disappeared"

    # 2. Under noDaT (Setting 2)
    res_nodat = build_solver_run_result(
        solver_name="Test",
        solver_key="Test",
        instance=instance,
        solution=solution,
        setting=SimulationSetting.SETTING_2,
        fov_size=5,
    )
    assert res_nodat.frames[1].statuses["Agent_01"] == "parked"
    assert res_nodat.frames[2].statuses["Agent_01"] == "parked"


def test_four_state_solution_classification():
    """Verify solved, invalid, truncated, and failed classifications."""
    starts = {"Agent_01": Point(0, 0), "Agent_02": Point(1, 0)}
    goals = {"Agent_01": Point(1, 0), "Agent_02": Point(0, 0)}
    instance = MAPFInstance(
        starts=starts,
        goals=goals,
        grid_width=4,
        grid_height=4,
        obstacles=set(),
    )

    # 1. Invalid solution (vertex collision at (0,0) at t=1)
    sol_invalid = MAPFSolution(
        solver_name="Test",
        is_centralized=False,
        success=True,  # Even if solver claims success, independent validator must catch invalidity!
        paths={
            "Agent_01": Path(points=[Point(0, 0), Point(0, 0)]),
            "Agent_02": Path(points=[Point(1, 0), Point(0, 0)]),
        },
        makespan=1,
    )
    res_inv = build_solver_run_result(
        "T", "T", instance, sol_invalid, SimulationSetting.SETTING_4, 5
    )
    assert res_inv.status == "invalid"
    assert res_inv.success is False

    # 2. Truncated solution (makespan >= max_steps without arrival)
    sol_trunc = MAPFSolution(
        solver_name="Test",
        is_centralized=False,
        success=False,
        paths={
            "Agent_01": Path(points=[Point(0, 0), Point(0, 0)]),
            "Agent_02": Path(points=[Point(1, 0), Point(1, 0)]),
        },
        makespan=50,
    )
    res_trunc = build_solver_run_result(
        "T", "T", instance, sol_trunc, SimulationSetting.SETTING_4, 5, max_steps=50
    )
    assert res_trunc.status == "truncated"
    assert res_trunc.success is False

    # 3. Solved solution
    sol_solved = MAPFSolution(
        solver_name="Test",
        is_centralized=False,
        success=True,
        paths={
            "Agent_01": Path(
                points=[Point(0, 0), Point(0, 1), Point(1, 1), Point(1, 0)]
            ),
            "Agent_02": Path(
                points=[Point(1, 0), Point(1, 0), Point(0, 0), Point(0, 0)]
            ),
        },
        makespan=3,
    )
    res_solved = build_solver_run_result(
        "T", "T", instance, sol_solved, SimulationSetting.SETTING_4, 5
    )
    assert res_solved.status == "solved"
    assert res_solved.success is True


def test_gui_simulate_endpoint_and_comparison(test_client: TestClient):
    """Validate API request/response schema, provenance headers, and comparison without overrides."""
    payload = {
        "grid_width": 8,
        "grid_height": 8,
        "agent_count": 2,
        "solver": "HeatMap",
        "compare_solver": "HeatMap",
        "commitment_type": "SC",
        "compare_commitment_type": "ZC",
        "fov_size": 5,
        "obstacle_density": 0.0,
        "setting": 4,
        "initial_tokens": 5,
        "max_steps": 30,
        "random_seed": 42,
    }
    resp = test_client.post("/api/simulate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    # Verify Pydantic schema contract
    validated_response = SimulationResponse.model_validate(data)
    assert validated_response.instance_hash != ""
    assert validated_response.run_id != ""
    assert validated_response.primary.solver_key == "HeatMap"
    assert validated_response.comparison is not None
    assert validated_response.comparison.solver_key == "HeatMap"

    # Frame 0 check
    assert len(validated_response.frames) == validated_response.makespan + 1
    assert validated_response.frames[0].tick == 0


@pytest.mark.asyncio
async def test_sse_event_buffer_last_event_id_and_multi_client():
    """Test append-only event buffer, Last-Event-ID catchup, and multi-client parity."""
    mgr = BenchmarkTaskManager()
    task = mgr.create_and_start_task("quick_test")
    assert task.task_id.startswith("task-")

    # Wait for terminal events rather than guessing when the worker has finished.
    try:
        async with asyncio.timeout(15):
            events_client_a = [
                chunk async for chunk in mgr.stream_task_events(task.task_id)
            ]
            events_client_b = [
                chunk
                async for chunk in mgr.stream_task_events(task.task_id, last_event_id=2)
            ]
    finally:
        mgr.cancel_task(task.task_id)

    assert len(events_client_a) >= 4
    # Event IDs must be strictly sequential (1, 2, 3...)
    assert "id: 1" in events_client_a[0]

    # Client B must not have received id 1 or id 2
    assert not any("id: 1\n" in c for c in events_client_b)
    assert not any("id: 2\n" in c for c in events_client_b)
    assert any("id: 3\n" in c for c in events_client_b)

    # Terminal event must be cleanly delivered to both clients
    assert any("suite_finished" in c for c in events_client_a)
    assert any("suite_finished" in c for c in events_client_b)
