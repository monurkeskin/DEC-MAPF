"""Compatibility manager for in-process tasks created before HTTP admission retirement."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from mapf.core.models import SimulationConfig
from mapf.core.movingai import generate_benchmark_map, generate_stern_scenario
from mapf.gui._legacy_progress import BenchmarkTaskProgress
from mapf.gui._legacy_suites import suite_runs
from mapf.solvers.base import MAPFInstance, MAPFSolution
from mapf.solvers.decentralized import DecentralizedNegotiationSolver

__all__ = ["BenchmarkTaskManager", "BenchmarkTaskProgress", "benchmark_manager"]


def _inputs(run: dict[str, Any]) -> tuple[MAPFInstance, SimulationConfig]:
    obstacles = generate_benchmark_map(width=run["grid_size"], height=run["grid_size"],
                                       obstacle_density=run["obstacle_density"], seed=run["seed"])
    distance = (2, 12) if run["grid_size"] <= 16 else (4, 24)
    pairs = generate_stern_scenario(width=run["grid_size"], height=run["grid_size"],
        obstacles=obstacles, num_agents=run["k"], min_dist=distance[0], max_dist=distance[1], seed=run["seed"])
    instance = MAPFInstance(starts={f"A_{i + 1:02d}": pairs[i][0] for i in range(run["k"])},
        goals={f"A_{i + 1:02d}": pairs[i][1] for i in range(run["k"])},
        grid_width=run["grid_size"], grid_height=run["grid_size"], obstacles=obstacles)
    config = SimulationConfig(grid_width=run["grid_size"], grid_height=run["grid_size"],
        obstacles=obstacles, fov_size=run["fov"], setting=run["setting"],
        commitment_type=run["commitment"], initial_tokens=5, max_steps=200, random_seed=run["seed"])
    return instance, config


def _result_record(run: dict[str, Any], solution: MAPFSolution, index: int, runtime: float) -> dict[str, Any]:
    return {"run_index": index, "map_name": run["map_name"], "strategy": run["strategy"],
            "setting_name": run["setting"].name, "commitment": run["commitment"].name,
            "k": run["k"], "fov": run["fov"], "seed": run["seed"], "success": solution.success,
            "solved_count": solution.metrics.get("solved_count", run["k"] if solution.success else 0),
            "makespan": solution.makespan, "negotiations": solution.metrics.get("negotiation_count", 0),
            "is_rate": solution.metrics.get("information_sharing_rate", 0.0),
            "norm_path_diff": solution.metrics.get("norm_path_diff", 0.0), "runtime_ms": round(runtime, 1)}


class BenchmarkTaskManager:
    """Retain thread-safe cancellation and independent SSE subscription cursors."""

    def __init__(self) -> None:
        self._tasks: dict[str, BenchmarkTaskProgress] = {}
        self._lock = threading.Lock()

    def get_task(self, task_id: str) -> BenchmarkTaskProgress | None:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        return task.cancel() if task else False

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [task.summary() for task in self._tasks.values()]

    def create_and_start_task(self, suite_name: str, custom_params: dict[str, Any] | None = None) -> BenchmarkTaskProgress:
        runs = suite_runs(suite_name)
        task = BenchmarkTaskProgress(f"task-{uuid.uuid4().hex[:8]}", suite_name, len(runs))
        with self._lock:
            self._tasks[task.task_id] = task
        threading.Thread(target=self._run_benchmark_worker, args=(task, runs),
                         daemon=True, name=f"Worker-{task.task_id}").start()
        return task

    def _run_benchmark_worker(self, task: BenchmarkTaskProgress, runs: list[dict[str, Any]]) -> None:
        solvers = {name: DecentralizedNegotiationSolver(strategy=name) for name in ("HeatMap", "PathAware")}
        try:
            for index, run in enumerate(runs, 1):
                description = (f"{run['map_name']} | {run['strategy']} | {run['setting'].name} | "
                               f"k={run['k']} | FoV={run['fov']} | seed={run['seed']}")
                if not task.begin_run(description):
                    return
                started = time.perf_counter()
                instance, config = _inputs(run)
                solution = solvers.get(run["strategy"], solvers["HeatMap"]).solve(instance, config)
                record = _result_record(run, solution, index, (time.perf_counter() - started) * 1000.0)
                if not task.record_result(record):
                    return
            task.finish()
        except Exception as exc:  # noqa: BLE001
            task.fail(exc)

    async def stream_task_events(self, task_id: str, last_event_id: int | None = None) -> AsyncGenerator[str, None]:
        task = self.get_task(task_id)
        if not task:
            yield f"event: error\ndata: {json.dumps({'error': 'Task not found'})}\n\n"
            return
        cursor = max(0, int(last_event_id or 0))
        while True:
            events, terminal = task.events_snapshot(cursor)
            for event in events:
                cursor = event["id"]
                yield f"id: {cursor}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
                if event["type"] in ("suite_finished", "error", "task_cancelled"):
                    return
            if terminal:
                return
            await asyncio.sleep(0.2)


benchmark_manager = BenchmarkTaskManager()
