"""Bound native process time and output memory, with periodic diagnostic snapshots."""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO, Any


class _TailReader:
    def __init__(self, stream: IO[bytes]) -> None:
        self._tail = b""
        self._count = 0
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._read, args=(stream,), daemon=True)
        self.thread.start()

    def _read(self, stream: IO[bytes]) -> None:
        with stream:
            while chunk := stream.read(4096):
                with self._lock:
                    self._count += len(chunk)
                    self._tail = (self._tail + chunk)[-4000:]

    def snapshot(self) -> tuple[str, int]:
        with self._lock:
            return self._tail.decode("utf-8", errors="replace"), self._count


@dataclass(frozen=True)
class NativeProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def run_native(
    command: list[str],
    timeout: float,
    progress: Callable[[dict[str, Any]], None],
) -> NativeProcessResult:
    """Drain both pipes throughout execution; retain only their last 4,000 bytes.

    The native child inherits the worker's owned process group, so the supervisor
    can still terminate the whole job. Diagnostic snapshots never renew a deadline.
    """
    started = time.monotonic()
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
    )
    assert process.stdout is not None and process.stderr is not None
    stdout, stderr = _TailReader(process.stdout), _TailReader(process.stderr)
    timed_out = False

    def snapshot() -> None:
        out, out_bytes = stdout.snapshot()
        err, err_bytes = stderr.snapshot()
        progress(
            {
                "pid": process.pid,
                "elapsed_seconds": time.monotonic() - started,
                "exit_code": process.poll(),
                "timed_out": timed_out,
                "stdout": out,
                "stderr": err,
                "stdout_bytes": out_bytes,
                "stderr_bytes": err_bytes,
                "stdout_truncated": out_bytes > 4000,
                "stderr_truncated": err_bytes > 4000,
            }
        )

    try:
        snapshot()
        while process.poll() is None:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                timed_out = True
                break
            try:
                process.wait(timeout=min(0.5, remaining))
            except subprocess.TimeoutExpired:
                snapshot()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        # Native solvers are single processes. A misbehaving executable's detached
        # pipe holder must not make the adapter wait indefinitely for stream EOF.
        stdout.thread.join(timeout=1)
        stderr.thread.join(timeout=1)
    snapshot()
    return NativeProcessResult(
        process.returncode, stdout.snapshot()[0], stderr.snapshot()[0], timed_out
    )
