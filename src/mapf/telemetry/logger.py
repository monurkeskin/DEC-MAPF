"""Bounded telemetry with durable checked chunks and visible writer failures."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import queue
import re
import shutil
import threading
import types
import uuid
from pathlib import Path
from typing import Any, Self

from mapf.artifact_io import atomic_write, encode
from mapf.telemetry.hook import QueuedTelemetryHook, TelemetryHook
from mapf.telemetry.schema import SerializableEvent, normalize

_STOP = object()


class AsyncExperimentLogger:
    """Lossless bounded queue; backpressure and I/O failures end the run explicitly.

    A crash can lose at most the current unpublished batch plus queued events.
    Completed chunk files are recoverable using index.json (complete=false).
    The compatibility gzip stream is published only after a successful stop.
    """

    def __init__(self, output_dir: Path | str, run_id: str | None = None,
                 buffer_flush_interval: int = 500, queue_capacity: int = 1024) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or f"run_{uuid.uuid4().hex}"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.run_id):
            raise ValueError("Run ID must be a plain identifier")
        if not 1 <= buffer_flush_interval <= 10000 or not 1 <= queue_capacity <= 10000:
            raise ValueError("Telemetry queue and flush bounds must be 1..10000")
        self.buffer_flush_interval = buffer_flush_interval
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=queue_capacity)
        self._hook = QueuedTelemetryHook(emit=self._enqueue)
        self._events_file_path = self.output_dir / f"{self.run_id}_events.jsonl.gz"
        self.chunks_dir = self.output_dir / f"{self.run_id}_chunks"
        self._worker_thread: threading.Thread | None = None
        self._running = False
        self._started = False
        self._stop_sent = False
        self._error: BaseException | None = None
        self._sequence = 0
        self._lock = threading.Lock()
        self._total_events_written = 0
        self._chunks: list[dict[str, Any]] = []

    @property
    def hook(self) -> TelemetryHook:
        return self._hook

    @property
    def events_file_path(self) -> Path:
        return self._events_file_path

    def _check_error(self) -> None:
        if self._error is not None:
            raise RuntimeError(f"Telemetry writer failed: {self._error}") from self._error

    def _enqueue(self, event: SerializableEvent) -> None:
        with self._lock:
            self._check_error()
            if not self._running:
                raise RuntimeError("Telemetry logger is not accepting events")
            record = normalize(event, self._sequence + 1)
            record["run_id"] = self.run_id
            # Snapshot mutable nested fields before the producer continues.
            payload = json.dumps(record, separators=(",", ":"), allow_nan=False).encode() + b"\n"
            try:
                self._queue.put(payload, timeout=2)
            except queue.Full:
                self._check_error()
                raise RuntimeError("Telemetry backpressure exceeded two seconds") from None
            self._sequence += 1
            self._check_error()

    def start(self) -> None:
        if self._running:
            return
        if self._started or self._events_file_path.exists():
            raise ValueError("A telemetry run is immutable; use a new run ID")
        self.chunks_dir.mkdir()  # exclusive ownership; never overwrite another run
        self._started = self._running = True
        try:
            self._index(False)
            self._worker_thread = threading.Thread(target=self._drain_queue, name=f"Telemetry-{self.run_id}", daemon=True)
            self._worker_thread.start()
        except BaseException as exc:
            self._running = False
            self._error = exc
            raise

    def stop(self) -> None:
        if not self._running and not self._writer_alive():
            self._check_error()
            return
        with self._lock:
            self._running = False
            self._check_error()
            self._request_stop()
        assert self._worker_thread is not None
        self._worker_thread.join(timeout=10)
        if self._worker_thread.is_alive():
            raise RuntimeError("Telemetry writer exceeded its shutdown deadline")
        self._check_error()

    def _writer_alive(self) -> bool:
        return self._worker_thread is not None and self._worker_thread.is_alive()

    def _request_stop(self) -> None:
        if self._stop_sent:
            return
        try:
            self._queue.put(_STOP, timeout=2)
        except queue.Full:
            self._check_error()
            raise RuntimeError("Telemetry could not drain within shutdown budget") from None
        self._stop_sent = True

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc_val: BaseException | None, exc_tb: types.TracebackType | None) -> None:
        self.stop()

    def _index(self, complete: bool) -> None:
        atomic_write(self.chunks_dir / "index.json", encode({
            "schema_version": "telemetry-2", "run_id": self.run_id,
            "complete": complete, "events": self._total_events_written, "chunks": self._chunks,
        }))

    def _flush_batch(self, batch: list[bytes]) -> None:
        data = gzip.compress(b"".join(batch), mtime=0)
        filename = f"events-{len(self._chunks):06d}.jsonl.gz"
        atomic_write(self.chunks_dir / filename, data)
        self._chunks.append({"file": filename, "sha256": hashlib.sha256(data).hexdigest(), "count": len(batch)})
        self._total_events_written += len(batch)
        self._index(False)

    def _drain_queue(self) -> None:
        try:
            self._consume_queue()
            self._publish_stream()
        except BaseException as exc:  # noqa: BLE001 - preserve background failure for the producer and stop()
            self._error = exc

    def _consume_queue(self) -> None:
        batch: list[bytes] = []
        while True:
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                if batch:
                    self._flush_batch(batch)
                    batch.clear()
                continue
            if item is _STOP:
                if batch:
                    self._flush_batch(batch)
                return
            batch.append(item)
            if len(batch) >= self.buffer_flush_interval:
                self._flush_batch(batch)
                batch.clear()

    def _publish_stream(self) -> None:
        # Concatenated gzip members are a standard gzip stream. No full-log RAM copy.
        tmp = self.chunks_dir / "complete.tmp"
        with tmp.open("xb") as target:
            for chunk in self._chunks:
                with (self.chunks_dir / chunk["file"]).open("rb") as source:
                    shutil.copyfileobj(source, target)
            if not self._chunks:
                target.write(gzip.compress(b"", mtime=0))
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, self._events_file_path)
        directory_fd = os.open(self.output_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        self._index(True)
