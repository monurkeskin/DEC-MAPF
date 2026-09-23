"""Locked progress transitions and an append-only stream for legacy batch tasks."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenchmarkTaskProgress:
    task_id: str
    suite_name: str
    total_runs: int
    completed_runs: int = 0
    start_time: float = field(default_factory=time.time)
    elapsed_sec: float = 0.0
    status: str = "RUNNING"
    current_run_info: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    cancelled: bool = False
    _events: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _append(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "id": len(self._events) + 1,
            "type": event_type,
            "task_id": self.task_id,
            **data,
        }
        self._events.append(payload)
        return payload

    def append_event(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._append(event_type, data)

    def events_snapshot(self, cursor: int) -> tuple[list[dict[str, Any]], bool]:
        with self._lock:
            return list(self._events[max(0, cursor) :]), self.status != "RUNNING"

    def get_events_after(self, cursor: int) -> list[dict[str, Any]]:
        return self.events_snapshot(cursor)[0]

    def total_events_count(self) -> int:
        with self._lock:
            return len(self._events)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "task_id": self.task_id,
                "suite_name": self.suite_name,
                "total_runs": self.total_runs,
                "completed_runs": self.completed_runs,
                "elapsed_sec": round(self.elapsed_sec, 1),
                "status": self.status,
                "current_run_info": self.current_run_info,
            }

    def cancel(self) -> bool:
        with self._lock:
            if self.status != "RUNNING":
                return False
            self.cancelled = True
            self.status = "CANCELLED"
            self._append(
                "task_cancelled", {"message": "Task was cancelled by user request."}
            )
            return True

    def begin_run(self, description: str) -> bool:
        with self._lock:
            if self.cancelled or self.status != "RUNNING":
                return False
            self.current_run_info = description
            return True

    def record_result(self, result: dict[str, Any]) -> bool:
        with self._lock:
            if self.status != "RUNNING":
                return False
            self.completed_runs = result["run_index"]
            self.elapsed_sec = time.time() - self.start_time
            self.results.append(result)
            self._append(
                "run_completed",
                {
                    "completed_runs": self.completed_runs,
                    "total_runs": self.total_runs,
                    "progress_pct": round(
                        self.completed_runs / self.total_runs * 100, 1
                    ),
                    "elapsed_sec": round(self.elapsed_sec, 1),
                    "current_run": result,
                },
            )
            return True

    def finish(self) -> None:
        with self._lock:
            if self.status != "RUNNING":
                return
            self.status = "COMPLETED"
            self.current_run_info = (
                "All runs finished; inspect individual solution outcomes."
            )
            successes = sum(1 for row in self.results if row["success"])
            self._append(
                "suite_finished",
                {
                    "status": "COMPLETED",
                    "total_runs": self.total_runs,
                    "elapsed_sec": round(self.elapsed_sec, 1),
                    "summary": {
                        "total": len(self.results),
                        "success_count": successes,
                        "success_rate": round(
                            successes / max(1, len(self.results)) * 100, 1
                        ),
                    },
                },
            )

    def fail(self, error: Exception) -> None:
        with self._lock:
            if self.status != "RUNNING":
                return
            self.status = "FAILED"
            self.error_message = str(error)
            self._append("error", {"error": str(error)})
