"""POSIX lifetime boundary for a worker and its native solver descendants.

The local supervisor already requires POSIX file locks. Each spawned job creates
its own session before invoking any solver. Only that job's process group is
signalled; application, GUI and unrelated experiment processes are never members.
"""

from __future__ import annotations

import os
import signal
import threading
from collections.abc import Callable
from typing import Any


def stop_owned_group(pid: int) -> None:
    """Stop the private group whose ID was reserved by the spawned job PID."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # Startup may have been cancelled before setsid(), or all have exited.


def run_owned_process(
    worker: Callable[..., None],
    job: dict[str, Any],
    output: str,
    parent_connection: Any,
) -> None:
    os.setsid()

    def watch_parent() -> None:
        try:
            parent_connection.recv_bytes()
        except (EOFError, OSError):
            stop_owned_group(os.getpid())
            os._exit(70)

    threading.Thread(target=watch_parent, daemon=True).start()
    worker(job, output, parent_connection)
