"""Thread-safe background batch benchmark task manager for MAPF GUI Dashboard.

Implements:
- Append-only event buffer with sequential event IDs.
- Last-Event-ID header and query cursor support for multi-client SSE reconnection.
- Safe thread-server concurrency and error propagation.
- Support for task cancellation and progress tracking.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from mapf.core.models import CommitmentType, SimulationConfig, SimulationSetting
from mapf.core.movingai import generate_benchmark_map, generate_stern_scenario
from mapf.solvers.base import MAPFInstance
from mapf.solvers.decentralized import DecentralizedNegotiationSolver


@dataclass
class BenchmarkTaskProgress:
    task_id: str
    suite_name: str
    total_runs: int
    completed_runs: int = 0
    start_time: float = field(default_factory=time.time)
    elapsed_sec: float = 0.0
    status: str = "RUNNING"  # RUNNING, COMPLETED, FAILED, CANCELLED
    current_run_info: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    cancelled: bool = False

    # Append-only event buffer with sequential IDs
    _events: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append_event(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            event_id = len(self._events) + 1
            payload = {
                "id": event_id,
                "type": event_type,
                "task_id": self.task_id,
                **data,
            }
            self._events.append(payload)
            return payload

    def get_events_after(self, cursor: int) -> list[dict[str, Any]]:
        with self._lock:
            if cursor < len(self._events):
                return list(self._events[cursor:])
            return []

    def total_events_count(self) -> int:
        with self._lock:
            return len(self._events)


class BenchmarkTaskManager:
    """Manages background batch benchmark executions and SSE progress streaming."""

    def __init__(self) -> None:
        self._tasks: dict[str, BenchmarkTaskProgress] = {}
        self._lock = threading.Lock()

    def get_task(self, task_id: str) -> BenchmarkTaskProgress | None:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            task.cancelled = True
            task.status = "CANCELLED"
            task.append_event(
                "task_cancelled",
                {
                    "task_id": task_id,
                    "message": "Task was cancelled by user request.",
                },
            )
            return True

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "task_id": t.task_id,
                    "suite_name": t.suite_name,
                    "total_runs": t.total_runs,
                    "completed_runs": t.completed_runs,
                    "elapsed_sec": round(t.elapsed_sec, 1),
                    "status": t.status,
                    "current_run_info": t.current_run_info,
                }
                for t in self._tasks.values()
            ]

    def create_and_start_task(
        self,
        suite_name: str,
        custom_params: dict[str, Any] | None = None,
    ) -> BenchmarkTaskProgress:
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        # Define runs based on suite
        runs: list[dict[str, Any]] = []
        if suite_name == "quick_test":
            for seed in [42, 101]:
                for strat in ["HeatMap", "PathAware"]:
                    runs.append({
                        "map_name": "empty-16-16",
                        "grid_size": 16,
                        "obstacle_density": 0.0,
                        "k": 20,
                        "setting": SimulationSetting.SETTING_4,
                        "commitment": CommitmentType.ZERO,
                        "strategy": strat,
                        "fov": 5,
                        "seed": seed,
                    })
        elif suite_name == "appendix_32x32":
            seeds = [42, 101, 137, 256]
            maps = [
                ("empty-32-32", 0.0),
                ("random-32-32-10", 0.10),
                ("random-32-32-20", 0.20),
            ]
            for map_name, density in maps:
                for setting in [
                    SimulationSetting.SETTING_1,
                    SimulationSetting.SETTING_2,
                    SimulationSetting.SETTING_3,
                    SimulationSetting.SETTING_4,
                ]:
                    for fov in [5, 7, 9]:
                        for seed in seeds:
                            runs.append({
                                "map_name": map_name,
                                "grid_size": 32,
                                "obstacle_density": density,
                                "k": 80,
                                "setting": setting,
                                "commitment": CommitmentType.ZERO,
                                "strategy": "HeatMap",
                                "fov": fov,
                                "seed": seed,
                            })
        elif suite_name == "commitment_types":
            seeds = [42, 101, 137, 256]
            for setting in [SimulationSetting.SETTING_3, SimulationSetting.SETTING_4]:
                for comm in [CommitmentType.STANDARD, CommitmentType.DYNAMIC, CommitmentType.ZERO]:
                    for fov in [5, 7, 9]:
                        for seed in seeds:
                            runs.append({
                                "map_name": "empty-16-16",
                                "grid_size": 16,
                                "obstacle_density": 0.0,
                                "k": 80,
                                "setting": setting,
                                "commitment": comm,
                                "strategy": "HeatMap",
                                "fov": fov,
                                "seed": seed,
                            })
        else:  # main_matrix default
            seeds = [42, 101, 137, 256]
            for strat in ["HeatMap", "PathAware"]:
                for setting in [
                    SimulationSetting.SETTING_1,
                    SimulationSetting.SETTING_2,
                    SimulationSetting.SETTING_3,
                    SimulationSetting.SETTING_4,
                ]:
                    for k in [20, 40, 60, 80]:
                        for seed in seeds:
                            runs.append({
                                "map_name": "empty-16-16",
                                "grid_size": 16,
                                "obstacle_density": 0.0,
                                "k": k,
                                "setting": setting,
                                "commitment": CommitmentType.ZERO,
                                "strategy": strat,
                                "fov": 5,
                                "seed": seed,
                            })

        task = BenchmarkTaskProgress(
            task_id=task_id,
            suite_name=suite_name,
            total_runs=len(runs),
        )

        with self._lock:
            self._tasks[task_id] = task

        # Launch worker in background thread
        thread = threading.Thread(
            target=self._run_benchmark_worker,
            args=(task, runs),
            daemon=True,
            name=f"Worker-{task_id}",
        )
        thread.start()
        return task

    def _run_benchmark_worker(
        self,
        task: BenchmarkTaskProgress,
        runs: list[dict[str, Any]],
    ) -> None:
        solvers: dict[str, DecentralizedNegotiationSolver] = {
            "HeatMap": DecentralizedNegotiationSolver(strategy="HeatMap"),
            "PathAware": DecentralizedNegotiationSolver(strategy="PathAware"),
        }

        try:
            for idx, r in enumerate(runs, 1):
                if task.cancelled:
                    return

                run_start = time.perf_counter()
                task.current_run_info = (
                    f"{r['map_name']} | {r['strategy']} | {r['setting'].name} | "
                    f"k={r['k']} | FoV={r['fov']} | seed={r['seed']}"
                )

                # Generate scenario
                obstacles = generate_benchmark_map(
                    width=r["grid_size"],
                    height=r["grid_size"],
                    obstacle_density=r["obstacle_density"],
                    seed=r["seed"],
                )
                min_d = 2 if r["grid_size"] <= 16 else 4
                max_d = 12 if r["grid_size"] <= 16 else 24
                pairs = generate_stern_scenario(
                    width=r["grid_size"],
                    height=r["grid_size"],
                    obstacles=obstacles,
                    num_agents=r["k"],
                    min_dist=min_d,
                    max_dist=max_d,
                    seed=r["seed"],
                )
                starts = {f"A_{i + 1:02d}": pairs[i][0] for i in range(r["k"])}
                goals = {f"A_{i + 1:02d}": pairs[i][1] for i in range(r["k"])}

                instance = MAPFInstance(
                    starts=starts,
                    goals=goals,
                    grid_width=r["grid_size"],
                    grid_height=r["grid_size"],
                    obstacles=obstacles,
                )
                config = SimulationConfig(
                    grid_width=r["grid_size"],
                    grid_height=r["grid_size"],
                    obstacles=obstacles,
                    fov_size=r["fov"],
                    setting=r["setting"],
                    commitment_type=r["commitment"],
                    initial_tokens=5,
                    max_steps=200,
                    random_seed=r["seed"],
                )

                solver = solvers.get(r["strategy"], solvers["HeatMap"])
                sol = solver.solve(instance, config)
                run_dur_ms = (time.perf_counter() - run_start) * 1000.0

                result_record = {
                    "run_index": idx,
                    "map_name": r["map_name"],
                    "strategy": r["strategy"],
                    "setting_name": r["setting"].name,
                    "commitment": r["commitment"].name,
                    "k": r["k"],
                    "fov": r["fov"],
                    "seed": r["seed"],
                    "success": sol.success,
                    "solved_count": sol.metrics.get("solved_count", r["k"] if sol.success else 0),
                    "makespan": sol.makespan,
                    "negotiations": sol.metrics.get("negotiation_count", 0),
                    "is_rate": sol.metrics.get("information_sharing_rate", 0.0),
                    "norm_path_diff": sol.metrics.get("norm_path_diff", 0.0),
                    "runtime_ms": round(run_dur_ms, 1),
                }

                task.completed_runs = idx
                task.elapsed_sec = time.time() - task.start_time
                task.results.append(result_record)

                # Append run_completed event
                task.append_event(
                    "run_completed",
                    {
                        "completed_runs": idx,
                        "total_runs": task.total_runs,
                        "progress_pct": round((idx / task.total_runs) * 100, 1),
                        "elapsed_sec": round(task.elapsed_sec, 1),
                        "current_run": result_record,
                    },
                )

            task.status = "COMPLETED"
            task.current_run_info = "All runs finished successfully."
            task.append_event(
                "suite_finished",
                {
                    "status": "COMPLETED",
                    "total_runs": task.total_runs,
                    "elapsed_sec": round(task.elapsed_sec, 1),
                    "summary": {
                        "total": len(task.results),
                        "success_count": sum(1 for res in task.results if res["success"]),
                        "success_rate": round(
                            sum(1 for res in task.results if res["success"])
                            / max(1, len(task.results))
                            * 100,
                            1,
                        ),
                    },
                },
            )

        except Exception as exc:  # noqa: BLE001
            task.status = "FAILED"
            task.error_message = str(exc)
            task.append_event(
                "error",
                {
                    "error": str(exc),
                },
            )

    async def stream_task_events(
        self,
        task_id: str,
        last_event_id: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream SSE events with Last-Event-ID catchup and cursor per subscriber."""
        task = self.get_task(task_id)
        if not task:
            yield f"event: error\ndata: {json.dumps({'error': 'Task not found'})}\n\n"
            return

        cursor = int(last_event_id or 0)

        while True:
            # 1. Catch up on all events beyond subscriber cursor
            new_events = task.get_events_after(cursor)
            if new_events:
                for ev in new_events:
                    ev_id = ev["id"]
                    ev_type = ev["type"]
                    cursor = ev_id
                    yield f"id: {ev_id}\nevent: {ev_type}\ndata: {json.dumps(ev)}\n\n"
                    if ev_type in ("suite_finished", "error", "task_cancelled"):
                        return

            # 2. Check if terminal state was reached and all events delivered
            if task.status in ("COMPLETED", "FAILED", "CANCELLED"):
                remaining = task.get_events_after(cursor)
                for ev in remaining:
                    ev_id = ev["id"]
                    ev_type = ev["type"]
                    cursor = ev_id
                    yield f"id: {ev_id}\nevent: {ev_type}\ndata: {json.dumps(ev)}\n\n"
                return

            # 3. Wait briefly before checking for new events or sending heartbeat
            await asyncio.sleep(0.2)


# Global benchmark manager instance
benchmark_manager = BenchmarkTaskManager()
