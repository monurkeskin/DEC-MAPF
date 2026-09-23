"""Compatibility routes for already-created legacy tasks; launches remain retired."""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from mapf.gui.batch_manager import benchmark_manager
from mapf.gui.schemas import BatchBenchmarkRequest

api = APIRouter()

@api.post("/api/benchmark/start")
async def start_benchmark(req: BatchBenchmarkRequest) -> dict[str, Any]:
    raise HTTPException(410, "Legacy benchmark launch is retired. Preview and run an explicit budgeted /api/v1/experiments manifest, or use mapf batch.")

@api.post("/api/benchmark/cancel/{task_id}")
async def cancel_benchmark(task_id: str) -> dict[str, Any]:
    if benchmark_manager.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    success = benchmark_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=409, detail="Task has already terminated")
    return {"task_id": task_id, "status": "CANCELLED"}

@api.get("/api/benchmark/status/{task_id}")
async def get_benchmark_status(task_id: str) -> dict[str, Any]:
    task = benchmark_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Benchmark task not found")
    return {
        "task_id": task.task_id,
        "suite_name": task.suite_name,
        "total_runs": task.total_runs,
        "completed_runs": task.completed_runs,
        "elapsed_sec": round(task.elapsed_sec, 1),
        "status": task.status,
        "current_run_info": task.current_run_info,
        "results_count": len(task.results),
        "error": task.error_message,
    }

@api.get("/api/benchmark/stream/{task_id}")
async def stream_benchmark_events(
    task_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    cursor: int | None = Query(default=None),
) -> StreamingResponse:
    """SSE stream endpoint supporting Last-Event-ID header and cursor query."""
    task = benchmark_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Benchmark task not found")

    # Prioritize Last-Event-ID header, fallback to cursor query parameter
    resolved_cursor: int | None = None
    if last_event_id:
        try:
            resolved_cursor = int(last_event_id)
        except ValueError:
            resolved_cursor = None
    elif cursor is not None:
        resolved_cursor = cursor

    return StreamingResponse(
        benchmark_manager.stream_task_events(
            task_id, last_event_id=resolved_cursor
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@api.get("/api/benchmark/tasks")
async def list_benchmark_tasks() -> list[dict[str, Any]]:
    return benchmark_manager.list_tasks()
