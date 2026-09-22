"""Durable local run repository: SQLite journal and immutable, checked JSON artifacts.

A final artifact is fsynced and renamed before its database row is committed.
A crash between those steps leaves an undiscoverable orphan, never a false success.
Only the single owning supervisor may recover pending jobs or clean its staging files.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal, cast

from mapf.application.contracts import JobEvent
from mapf.artifact_io import (
    atomic_write as atomic_write,  # noqa: PLC0414 - typed compatibility re-export
)
from mapf.artifact_io import (
    encode as encode,  # noqa: PLC0414 - typed compatibility re-export
)

TERMINAL = frozenset({"completed", "failed", "cancelled", "timed_out", "interrupted"})
ID_PATTERN = re.compile(r"^(run|job|attempt|scenario|batch)-[a-f0-9]{32}$")
WORKSPACE_SCHEMA_VERSION = 1
_REQUIRED_COLUMNS = {
    "jobs": {"id", "command_key", "request_digest", "body", "created"},
    "events": {"job_id", "sequence", "body"},
    "runs": {"id", "sha256", "summary", "created", "pinned"},
    "scenarios": {"id", "body"},
    "batches": {"command_key", "request_digest", "receipt"},
}


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value)).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def check_id(value: str) -> str:
    if not ID_PATTERN.fullmatch(value):
        raise ValueError("Malformed resource identifier")
    return value


class RunRepository:
    def __init__(
        self, base_dir: str | Path, quota_bytes: int = 512 * 1024 * 1024,
        *, create: bool = True, read_only: bool = False,
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.artifacts = self.base_dir / "artifacts"
        self.staging = self.base_dir / "staging"
        self.db_path = self.base_dir / "workspace.sqlite3"
        self.quota_bytes = quota_bytes
        self.read_only = read_only
        self._progress_cache: OrderedDict[str, tuple[tuple[Any, ...], bool]] = OrderedDict()
        self._progress_lock = threading.Lock()
        existing = self.db_path.is_file()
        if not existing and (not create or read_only):
            raise FileNotFoundError(f"Workspace does not exist: {self.base_dir}")
        if existing:
            self.inspect_schema()
        if read_only:
            return
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts.mkdir(exist_ok=True)
        self.staging.mkdir(exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, command_key TEXT UNIQUE, request_digest TEXT NOT NULL,
                    body TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    job_id TEXT NOT NULL, sequence INTEGER NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(job_id, sequence));
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, summary TEXT NOT NULL,
                    created REAL NOT NULL, pinned INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS batches (
                    command_key TEXT PRIMARY KEY, request_digest TEXT NOT NULL, receipt TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS jobs_state ON jobs(json_extract(body, '$.state'));
            """)
            if not existing:
                db.execute(f"PRAGMA user_version={WORKSPACE_SCHEMA_VERSION}")

    @classmethod
    def open_existing(cls, base_dir: str | Path, *, read_only: bool = True) -> RunRepository:
        """Open an existing compatible journal; inspection never initializes storage."""
        return cls(base_dir, create=False, read_only=read_only)

    def inspect_schema(self) -> int:
        """Version 0 is the original unversioned schema; inspection never migrates it."""
        try:
            db = sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True)
            try:
                version = int(db.execute("PRAGMA user_version").fetchone()[0])
                if version not in (0, WORKSPACE_SCHEMA_VERSION):
                    raise ValueError(f"Unsupported workspace schema {version}; supported: 0, {WORKSPACE_SCHEMA_VERSION}")
                for table, required in _REQUIRED_COLUMNS.items():
                    columns = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
                    if not required <= columns:
                        raise ValueError(f"Incompatible workspace: {table} schema is incomplete")
                return version
            finally:
                db.close()
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"Invalid workspace database: {exc}") from exc

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = (sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=10)
              if self.read_only else sqlite3.connect(self.db_path, timeout=10))
        try:
            with db:
                yield db
        finally:
            db.close()

    def usage_bytes(self) -> int:
        total = 0
        for path in self.base_dir.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except FileNotFoundError:
                # Concurrent SQLite checkpoint/staging publication can remove an
                # entry after traversal. Real permission/I/O failures still surface.
                continue
        return total

    def ensure_space(self, additional: int) -> None:
        if self.usage_bytes() + additional > self.quota_bytes:
            raise OSError(
                "Workspace disk quota exceeded; export or delete unpinned runs"
            )

    def admit(
        self,
        body: dict[str, Any],
        command_key: str | None,
        request_digest: str,
        max_pending: int = 32,
    ) -> tuple[dict[str, Any], bool]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if command_key:
                row = db.execute(
                    "SELECT request_digest,body FROM jobs WHERE command_key=?",
                    (command_key,),
                ).fetchone()
                if row:
                    if row[0] != request_digest:
                        raise ValueError(
                            "Idempotency key was already used for a different request"
                        )
                    return json.loads(row[1]), False
            pending = db.execute("SELECT count(*) FROM jobs WHERE json_extract(body,'$.state') IN ('pending','running')").fetchone()[0]
            if pending >= max_pending:
                raise OverflowError("Local queue capacity reached")
            self.ensure_space(256 * 1024)
            db.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?)",
                (
                    body["job_id"],
                    command_key,
                    request_digest,
                    encode(body).decode(),
                    body["created_at"],
                ),
            )
            self._event(db, body, "status")
        return body, True

    def admit_batch(
        self,
        jobs: list[dict[str, Any]],
        command_key: str,
        request_digest: str,
        max_pending: int = 32,
    ) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT request_digest,receipt FROM batches WHERE command_key=?",
                (command_key,),
            ).fetchone()
            if existing:
                if existing[0] != request_digest:
                    raise ValueError(
                        "Idempotency key was already used for a different batch"
                    )
                return cast(dict[str, Any], json.loads(existing[1]))
            pending = sum(
                json.loads(row[0])["state"] not in TERMINAL
                for row in db.execute("SELECT body FROM jobs")
            )
            if pending + len(jobs) > max_pending:
                raise OverflowError("Batch exceeds available local queue capacity")
            self.ensure_space(len(jobs) * 256 * 1024)
            for j in jobs:
                db.execute(
                    "INSERT INTO jobs VALUES(?,?,?,?,?)",
                    (
                        j["job_id"],
                        None,
                        request_digest,
                        encode(j).decode(),
                        j["created_at"],
                    ),
                )
                self._event(db, j, "status")
            receipt = {
                "batch_id": jobs[0]["batch_id"],
                "jobs": [j["job_id"] for j in jobs],
                "plan_digest": request_digest,
            }
            db.execute(
                "INSERT INTO batches VALUES(?,?,?)",
                (command_key, request_digest, encode(receipt).decode()),
            )
            return receipt

    def _event(
        self,
        db: sqlite3.Connection,
        job: dict[str, Any],
        kind: Literal["status", "done", "diagnostic"],
        message: str | None = None,
    ) -> None:
        seq = db.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE job_id=?",
            (job["job_id"],),
        ).fetchone()[0]
        event = JobEvent(
            sequence=seq,
            job_id=job["job_id"],
            run_id=job["run_id"],
            attempt_id=job["attempt_id"],
            type=kind,
            timestamp=time.time(),
            state=job["state"],
            message=message,
        ).model_dump(mode="json")
        db.execute(
            "INSERT INTO events VALUES(?,?,?)",
            (job["job_id"], seq, encode(event).decode()),
        )

    def transition(self, job_id: str, state: str, **updates: Any) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT body FROM jobs WHERE id=?", (check_id(job_id),)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            job: dict[str, Any] = json.loads(row[0])
            if job["state"] in TERMINAL:
                return job  # late completion cannot resurrect cancellation
            allowed = {
                "pending": {"running", "cancelled", "interrupted", "failed"},
                "running": TERMINAL,
            }
            if state not in allowed[job["state"]]:
                raise ValueError(f"Illegal transition: {job['state']} -> {state}")
            job.update(updates, state=state)
            if state in TERMINAL:
                job["completed_at"] = time.time()
            db.execute(
                "UPDATE jobs SET body=? WHERE id=?", (encode(job).decode(), job_id)
            )
            self._event(
                db, job, "done" if state in TERMINAL else "status", job.get("error")
            )
        return job

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT body FROM jobs WHERE id=?", (check_id(job_id),)
            ).fetchone()
        if row is None:
            return None
        job: dict[str, Any] = json.loads(row[0])
        if job["state"] == "completed":
            run = self.get_run(job["run_id"], include_frames=False)
            job["result"] = run["result"] if run else None
        return job

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT body FROM jobs ORDER BY created DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def active_jobs(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT body FROM jobs WHERE json_extract(body,'$.state') IN ('pending','running') ORDER BY created").fetchall()
        return [json.loads(row[0]) for row in rows]

    def events(self, job_id: str, cursor: int = 0) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT body FROM events WHERE job_id=? AND sequence>? ORDER BY sequence",
                (check_id(job_id), cursor),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def recover(self) -> int:
        with self.connect() as db:
            jobs = [json.loads(r[0]) for r in db.execute("SELECT body FROM jobs")]
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiments'").fetchone():
                db.execute("UPDATE experiments SET state='interrupted' WHERE state='running'")
        count = 0
        for job in jobs:
            if job["state"] not in TERMINAL:
                self.transition(
                    job["job_id"],
                    "interrupted",
                    error="Supervisor restarted; explicit new attempt required",
                )
                count += 1
        for path in self.staging.glob("attempt-*.json"):
            path.unlink()
        # Final artifacts with no committed metadata are quarantined, not imported.
        with self.connect() as db:
            known = {row[0] for row in db.execute("SELECT id FROM runs")}
        for path in self.artifacts.glob("run-*.json"):
            if path.stem not in known:
                path.rename(self.staging / f"orphan-{path.name}")
        for path in self.artifacts.glob("run-*.frames-*.json.gz"):
            if path.name.split(".")[0] not in known:
                path.rename(self.staging / f"orphan-{path.name}")
        return count

    def save_run(self, payload: dict[str, Any], job_id: str | None = None) -> None:
        payload = deepcopy(payload)
        payload.pop("frames_index", None)
        meta = payload["metadata"]
        run_id = check_id(meta["run_id"])
        raw = encode(payload)
        if len(raw) > 50 * 1024 * 1024:
            raise ValueError("Replay exceeds the 50 MiB per-run artifact limit")
        self.ensure_space(len(raw) + 65536)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone():
                raise ValueError("Run artifacts are immutable")
            job: dict[str, Any] | None = None
            if job_id:
                row = db.execute(
                    "SELECT body FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
                job = json.loads(row[0])
                assert job is not None
                if job["state"] != "running":
                    return
            frames = payload.get("frames", [])
            if len(frames) > 32:
                index = []
                for offset in range(0, len(frames), 32):
                    part = frames[offset:offset + 32]
                    chunk = gzip.compress(encode(part), mtime=0)
                    filename = f"{run_id}.frames-{offset:06d}.json.gz"
                    atomic_write(self.artifacts / filename, chunk)
                    index.append({"offset": offset, "count": len(part), "file": filename,
                                  "sha256": hashlib.sha256(chunk).hexdigest()})
                payload["frames_index"] = index
                payload["frames"] = []
                payload["result"]["frames"] = []
                raw = encode(payload)
            atomic_write(self.artifacts / f"{run_id}.json", raw)
            summary = {
                k: meta[k]
                for k in (
                    "run_id",
                    "instance_hash",
                    "solver_name",
                    "setting",
                    "agent_count",
                    "grid_width",
                    "grid_height",
                    "success",
                    "is_valid",
                    "validation_status",
                    "makespan",
                    "sum_of_costs",
                    "runtime_ms",
                    "frame_count",
                    "timestamp",
                )
            }
            db.execute(
                "INSERT INTO runs(id,sha256,summary,created) VALUES(?,?,?,?)",
                (
                    run_id,
                    hashlib.sha256(raw).hexdigest(),
                    encode(summary).decode(),
                    meta["timestamp"],
                ),
            )
            if job:
                job.update(state="completed", completed_at=time.time())
                db.execute(
                    "UPDATE jobs SET body=? WHERE id=?", (encode(job).decode(), job_id)
                )
                self._event(db, job, "done")

    def get_run(self, run_id: str, *, include_frames: bool = True) -> dict[str, Any] | None:
        check_id(run_id)
        with self.connect() as db:
            row = db.execute("SELECT sha256 FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        raw = (self.artifacts / f"{run_id}.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != row[0]:
            raise ValueError("Artifact integrity check failed")
        payload = cast(dict[str, Any], json.loads(raw))
        if include_frames and payload.get("frames_index"):
            payload["frames"] = self._read_frames(payload, 0, payload["metadata"]["frame_count"])
            payload["result"]["frames"] = payload["frames"]
        elif not include_frames:
            payload["frames"] = []
            payload["result"]["frames"] = []
        return payload

    def verified_success(self, run_id: str, expected_sha256: str | None) -> bool | None:
        """Cache only a verified scalar outcome; changed files are always rechecked."""
        check_id(run_id)
        if expected_sha256 is None:
            with self._progress_lock:
                self._progress_cache.pop(run_id, None)
            return None
        path = self.artifacts / f"{run_id}.json"

        def signature() -> tuple[Any, ...]:
            stat = path.stat()
            return (expected_sha256, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

        try:
            before = signature()
            with self._progress_lock:
                cached = self._progress_cache.get(run_id)
                if cached and cached[0] == before:
                    self._progress_cache.move_to_end(run_id)
                    return cached[1]
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected_sha256:
                raise ValueError("Artifact integrity check failed")
            success = json.loads(raw)["result"]["success"]
            if not isinstance(success, bool):
                raise ValueError("Artifact success field must be boolean")  # noqa: TRY004 - invalid external artifact
            if before == signature():
                with self._progress_lock:
                    self._progress_cache[run_id] = (before, success)
                    self._progress_cache.move_to_end(run_id)
                    while len(self._progress_cache) > 10000:
                        self._progress_cache.popitem(last=False)
            return success
        except FileNotFoundError:
            with self._progress_lock:
                self._progress_cache.pop(run_id, None)
            return None

    def _read_frames(self, payload: dict[str, Any], offset: int, limit: int) -> list[dict[str, Any]]:
        if not payload.get("frames_index"):
            return cast(list[dict[str, Any]], payload["frames"][offset:offset + limit])
        result = []
        run_id = payload["metadata"]["run_id"]
        for chunk in payload["frames_index"]:
            start = chunk["offset"]
            if start + chunk["count"] <= offset or start >= offset + limit:
                continue
            filename = chunk["file"]
            if not re.fullmatch(re.escape(run_id) + r"\.frames-\d{6}\.json\.gz", filename):
                raise ValueError("Malformed frame chunk reference")
            raw = (self.artifacts / filename).read_bytes()
            if hashlib.sha256(raw).hexdigest() != chunk["sha256"]:
                raise ValueError("Frame chunk integrity check failed")
            decoded = json.loads(gzip.decompress(raw))
            if len(decoded) != chunk["count"]:
                raise ValueError("Frame chunk count mismatch")
            result.extend(decoded[max(0, offset-start):min(len(decoded), offset+limit-start)])
        return result

    def frame_slice(self, run_id: str, offset: int, limit: int) -> dict[str, Any]:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Frame slice requires a nonnegative offset and limit 1..100")
        # Read the checked small root, without materializing unrelated chunks.
        payload = self.get_run(run_id, include_frames=False)
        if payload is None:
            raise KeyError(run_id)
        if not payload.get("frames_index"):
            payload = self.get_run(run_id)
            assert payload is not None
        frames = self._read_frames(payload, offset, limit)
        return {"run_id": run_id, "offset": offset, "total": payload["metadata"]["frame_count"], "frames": frames}

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT summary,pinned FROM runs ORDER BY created DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(json.loads(row[0]), pinned=bool(row[1])) for row in rows]

    def pin(self, run_id: str, pinned: bool) -> None:
        with self.connect() as db:
            if not db.execute(
                "UPDATE runs SET pinned=? WHERE id=?", (pinned, check_id(run_id))
            ).rowcount:
                raise KeyError(run_id)

    def delete_run(self, run_id: str) -> None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT pinned FROM runs WHERE id=?", (check_id(run_id),)
            ).fetchone()
            if not row:
                raise KeyError(run_id)
            if row[0]:
                raise ValueError("Pinned runs cannot be deleted")
            db.execute("DELETE FROM runs WHERE id=?", (run_id,))
        (self.artifacts / f"{run_id}.json").unlink(missing_ok=True)
        for chunk in self.artifacts.glob(f"{run_id}.frames-*.json.gz"):
            chunk.unlink()

    def save_scenario(self, snapshot: dict[str, Any]) -> str:
        scenario_id = new_id("scenario")
        self.ensure_space(len(encode(snapshot)) + 16384)
        with self.connect() as db:
            db.execute(
                "INSERT INTO scenarios VALUES(?,?)",
                (scenario_id, encode(snapshot).decode()),
            )
        return scenario_id

    def get_scenario(self, scenario_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT body FROM scenarios WHERE id=?", (check_id(scenario_id),)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list_scenarios(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [
                dict(json.loads(row[1]), scenario_id=row[0])
                for row in db.execute("SELECT id,body FROM scenarios")
            ]
