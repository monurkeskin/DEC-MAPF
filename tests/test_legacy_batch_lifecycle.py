"""Cancellation and reconnect semantics for tasks created before route retirement."""

import asyncio
import json

import pytest

from mapf.core.models import CommitmentType, Point, SimulationSetting
from mapf.gui import batch_manager
from mapf.gui.batch_manager import BenchmarkTaskManager, BenchmarkTaskProgress
from mapf.solvers.base import MAPFSolution


@pytest.fixture
def task():
    manager = BenchmarkTaskManager()
    task = BenchmarkTaskProgress("task-test", "fixture", 1)
    manager._tasks[task.task_id] = task
    return manager, task


@pytest.fixture
def definition(monkeypatch):
    monkeypatch.setattr(batch_manager, "generate_benchmark_map", lambda **kw: set())
    monkeypatch.setattr(batch_manager, "generate_stern_scenario", lambda **kw: [(Point(0, 0), Point(1, 0))])
    return {"grid_size": 16, "map_name": "fixture", "obstacle_density": 0.0, "k": 1,
            "setting": SimulationSetting.SETTING_4, "commitment": CommitmentType.ZERO,
            "strategy": "HeatMap", "fov": 5, "seed": 42}


@pytest.mark.parametrize("terminal", ["COMPLETED", "FAILED", "CANCELLED"])
def test_cancel_preserves_a_terminal_outcome(task, terminal):
    manager, progress = task
    progress.status = terminal
    assert manager.cancel_task(progress.task_id) is False
    assert progress.status == terminal and progress.total_events_count() == 0


def test_repeated_cancel_adds_one_terminal_event(task):
    manager, progress = task
    assert manager.cancel_task(progress.task_id)
    assert not manager.cancel_task(progress.task_id)
    assert [e["type"] for e in progress.get_events_after(0)] == ["task_cancelled"]


@pytest.mark.parametrize("raises", [False, True])
def test_inflight_completion_cannot_overwrite_cancellation(task, definition, monkeypatch, raises):
    manager, progress = task

    def solve(self, instance, config):
        assert manager.cancel_task(progress.task_id)
        if raises:
            raise RuntimeError("late solver error")
        return MAPFSolution(solver_name="fixture", is_centralized=False, success=True)

    monkeypatch.setattr(batch_manager.DecentralizedNegotiationSolver, "solve", solve)
    manager._run_benchmark_worker(progress, [definition])
    assert progress.status == "CANCELLED"
    assert progress.completed_runs == 0 and progress.results == []
    assert [e["type"] for e in progress.get_events_after(0)] == ["task_cancelled"]


def test_cancelled_queue_does_not_enter_the_next_solver(task, definition, monkeypatch):
    manager, progress = task
    manager.cancel_task(progress.task_id)

    def unexpected(*args):
        pytest.fail("Cancelled task must not invoke a solver")

    monkeypatch.setattr(batch_manager.DecentralizedNegotiationSolver, "solve", unexpected)
    manager._run_benchmark_worker(progress, [definition])
    assert progress.completed_runs == 0


def test_failed_solver_records_error_and_stops_remaining_trials(task, definition, monkeypatch):
    manager, progress = task

    def solve(*args):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(batch_manager.DecentralizedNegotiationSolver, "solve", solve)
    manager._run_benchmark_worker(progress, [definition, definition])
    assert progress.status == "FAILED" and progress.error_message == "fixture failure"
    assert progress.get_events_after(0)[0]["error"] == "fixture failure"
    assert progress.completed_runs == 0


@pytest.mark.asyncio
async def test_reconnect_after_terminal_id_does_not_wait(task):
    manager, progress = task
    manager.cancel_task(progress.task_id)

    async def collect():
        return [event async for event in manager.stream_task_events(progress.task_id, last_event_id=1)]

    assert await asyncio.wait_for(collect(), timeout=1) == []


@pytest.mark.asyncio
async def test_unknown_task_has_one_error_event():
    events = [event async for event in BenchmarkTaskManager().stream_task_events("absent")]
    assert len(events) == 1 and json.loads(events[0].split("data: ")[1])["error"] == "Task not found"


def test_unknown_task_cannot_be_cancelled():
    assert not BenchmarkTaskManager().cancel_task("absent")


@pytest.mark.parametrize(("suite", "count", "size"), [
    ("quick_test", 4, 16), ("appendix_32x32", 144, 32),
    ("commitment_types", 72, 16), ("main_matrix", 128, 16), ("unknown", 128, 16),
])
def test_legacy_suite_admission_keeps_declared_population(monkeypatch, suite, count, size):
    calls = []

    class CapturedThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            calls.append(self.kwargs)

    monkeypatch.setattr(batch_manager.threading, "Thread", CapturedThread)
    manager = BenchmarkTaskManager()
    progress = manager.create_and_start_task(suite)
    runs = calls[0]["args"][1]
    assert progress.total_runs == count == len(runs)
    assert {run["grid_size"] for run in runs} == {size}
    assert manager.get_task(progress.task_id) is progress
    assert manager.list_tasks()[0]["status"] == "RUNNING"


@pytest.mark.parametrize("success", [False, True])
def test_worker_summary_distinguishes_completion_from_solved_trials(task, definition, monkeypatch, success):
    manager, progress = task
    definition["grid_size"] = 32
    generated = []

    def scenario(**kwargs):
        generated.append(kwargs)
        return [(Point(0, 0), Point(1, 0))]

    def solve(self, instance, config):
        assert config.initial_tokens == 5 and config.max_steps == 200 and config.random_seed == 42
        assert config.setting == SimulationSetting.SETTING_4
        assert instance.starts == {"A_01": Point(0, 0)}
        return MAPFSolution(solver_name="fixture", is_centralized=False, success=success)

    monkeypatch.setattr(batch_manager, "generate_stern_scenario", scenario)
    monkeypatch.setattr(batch_manager.DecentralizedNegotiationSolver, "solve", solve)
    manager._run_benchmark_worker(progress, [definition])
    assert generated[0]["min_dist"] == 4 and generated[0]["max_dist"] == 24
    assert progress.status == "COMPLETED" and progress.completed_runs == 1
    assert progress.results[0]["solved_count"] == int(success)
    summary = progress.get_events_after(0)[-1]["summary"]
    assert summary == {"total": 1, "success_count": int(success), "success_rate": 100.0 if success else 0.0}


def test_terminal_progress_ignores_stale_worker_notifications(task):
    manager, progress = task
    manager.cancel_task(progress.task_id)
    progress.finish()
    progress.fail(RuntimeError("stale notification"))
    assert progress.total_events_count() == 1 and progress.status == "CANCELLED"


@pytest.mark.asyncio
async def test_negative_reconnect_cursor_replays_from_first_event(task):
    manager, progress = task
    progress.append_event("run_completed", {})
    manager.cancel_task(progress.task_id)
    events = [event async for event in manager.stream_task_events(progress.task_id, last_event_id=-1)]
    assert len(events) == 2 and events[0].startswith("id: 1\n")
