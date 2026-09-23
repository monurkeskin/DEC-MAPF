"""Canonical JSON bytes and durable file replacement shared by independent adapters."""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import rfc8785


def encode(value: Any) -> bytes:
    return rfc8785.dumps(value)


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        tmp.unlink(missing_ok=True)
