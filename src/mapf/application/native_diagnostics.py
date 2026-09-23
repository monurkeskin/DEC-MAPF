"""One atomic native snapshot per attempt, recoverable after a worker is killed."""

import json
import time
from pathlib import Path
from typing import Any

from mapf.artifact_io import atomic_write, encode

_IDENTITY = ("job_id", "attempt_id", "run_id")


def diagnostic_path(output: str | Path) -> Path:
    return Path(output).with_suffix(".native.json")


def write_diagnostics(
    output: str | Path, job: dict[str, Any], details: dict[str, Any]
) -> None:
    value = {key: job[key] for key in _IDENTITY}
    value.update(observed_at=time.time(), diagnostics=details)
    atomic_write(diagnostic_path(output), encode(value))


def read_diagnostics(output: str | Path, job: dict[str, Any]) -> dict[str, Any]:
    path = diagnostic_path(output)
    if not path.exists():
        return {}
    if path.stat().st_size > 512 * 1024:
        return {"unavailable": "native snapshot exceeds 512 KiB"}
    try:
        value = json.loads(path.read_text())
        if any(value.get(key) != job[key] for key in _IDENTITY):
            raise ValueError("Native snapshot identity mismatch")
        details = value["diagnostics"]
        if not isinstance(details, dict):
            raise TypeError("Native snapshot diagnostics must be an object")
        return {
            **details,
            "observed_at": value["observed_at"],
            "scope": "Last native snapshot; no progress after its timestamp is inferred",
        }
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"unavailable": f"Invalid native snapshot: {exc}"}
