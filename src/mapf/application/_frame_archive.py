"""Checked frame chunks; journal transactions remain owned by RunRepository."""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from mapf.artifact_io import encode


class FrameArchive:
    """Write deterministic checked frame chunks and read only overlapping slices.

    ``compact`` updates its supplied publication payload in place. The caller
    supplies atomic writes and owns the journal transaction after publication.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def compact(self, payload: dict[str, Any], write: Callable[[Path, bytes], None]) -> bool:
        frames = payload.get("frames", [])
        if len(frames) <= 32:
            return False
        run_id = payload["metadata"]["run_id"]
        payload["frames_index"] = [self._write_chunk(run_id, offset, frames[offset:offset + 32], write)
                                   for offset in range(0, len(frames), 32)]
        payload["frames"] = []
        payload["result"]["frames"] = []
        return True

    def _write_chunk(self, run_id: str, offset: int, frames: list[dict[str, Any]],
                     write: Callable[[Path, bytes], None]) -> dict[str, Any]:
        data = gzip.compress(encode(frames), mtime=0)
        filename = f"{run_id}.frames-{offset:06d}.json.gz"
        write(self.directory / filename, data)
        return {"offset": offset, "count": len(frames), "file": filename,
                "sha256": hashlib.sha256(data).hexdigest()}

    def read(self, payload: dict[str, Any], offset: int, limit: int) -> list[dict[str, Any]]:
        if not payload.get("frames_index"):
            return cast(list[dict[str, Any]], payload["frames"][offset:offset + limit])
        result = []
        for chunk in payload["frames_index"]:
            start = chunk["offset"]
            if start + chunk["count"] <= offset or start >= offset + limit:
                continue
            decoded = self._read_chunk(payload["metadata"]["run_id"], chunk)
            result.extend(decoded[max(0, offset-start):min(len(decoded), offset+limit-start)])
        return result

    def _read_chunk(self, run_id: str, chunk: dict[str, Any]) -> list[dict[str, Any]]:
        filename = chunk["file"]
        if not re.fullmatch(re.escape(run_id) + r"\.frames-\d{6}\.json\.gz", filename):
            raise ValueError("Malformed frame chunk reference")
        raw = (self.directory / filename).read_bytes()
        if hashlib.sha256(raw).hexdigest() != chunk["sha256"]:
            raise ValueError("Frame chunk integrity check failed")
        decoded: list[dict[str, Any]] = json.loads(gzip.decompress(raw))
        if len(decoded) != chunk["count"]:
            raise ValueError("Frame chunk count mismatch")
        return decoded
