"""Experiment persistence boundary; execution policy does not issue SQL."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Protocol

from mapf.application.runs import RunRepository, digest, encode


class ExperimentStore(Protocol):
    def manifest(self, experiment_id: str) -> dict[str, Any]: ...
    def manifests(self) -> list[dict[str, Any]]: ...
    def attempts(self, experiment_id: str) -> dict[str, list[dict[str, Any]]]: ...
    def latest_attempts(self, experiment_id: str) -> dict[str, dict[str, Any]]: ...
    def trial_ids(self, experiment_id: str) -> list[str]: ...
    def progress(self, experiment_id: str) -> tuple[str, float]: ...
    def register(self, manifest: dict[str, Any], *, resume: bool) -> float: ...
    def update(self, experiment_id: str, state: str, elapsed: float) -> None: ...


class SQLiteExperimentStore:
    """Use the existing workspace database and schema without migrating old runs."""

    def __init__(self, repository: RunRepository) -> None:
        self.repository = repository
        if repository.read_only:
            return
        with repository.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY, manifest TEXT NOT NULL,
                    elapsed REAL NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'planned');
                CREATE INDEX IF NOT EXISTS jobs_experiment
                    ON jobs(json_extract(body, '$.experiment_id'));
            """)

    def manifest(self, experiment_id: str) -> dict[str, Any]:
        with self.repository.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='experiments' AND type='table'").fetchone():
                raise KeyError(experiment_id)
            row = db.execute("SELECT manifest FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        return dict(json.loads(row[0]))

    def manifests(self) -> list[dict[str, Any]]:
        with self.repository.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='experiments' AND type='table'").fetchone():
                return []
            return [{"experiment_id": row[0], "name": json.loads(row[1])["name"], "state": row[2],
                     "elapsed_seconds": row[3]} for row in db.execute("SELECT id,manifest,state,elapsed FROM experiments")]

    def attempts(self, experiment_id: str) -> dict[str, list[dict[str, Any]]]:
        with self.repository.connect() as db:
            records = db.execute("SELECT body FROM jobs WHERE json_extract(body, '$.experiment_id')=? ORDER BY created",
                                 (experiment_id,)).fetchall()
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            job = json.loads(record[0])
            result[job["trial_id"]].append(job)
        return dict(result)

    def progress(self, experiment_id: str) -> tuple[str, float]:
        with self.repository.connect() as db:
            row = db.execute("SELECT state,elapsed FROM experiments WHERE id=?", (experiment_id,)).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        return str(row[0]), float(row[1])

    def trial_ids(self, experiment_id: str) -> list[str]:
        with self.repository.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='experiments' AND type='table'").fetchone():
                raise KeyError(experiment_id)
            records = db.execute("SELECT json_extract(t.value,'$.trial_id') FROM experiments e, "
                "json_each(e.manifest,'$.trials') t WHERE e.id=?", (experiment_id,)).fetchall()
        if not records:
            raise KeyError(experiment_id)
        return [str(row[0]) for row in records]

    def latest_attempts(self, experiment_id: str) -> dict[str, dict[str, Any]]:
        """Project scheduling fields in SQLite; leave full history available for export."""
        with self.repository.connect() as db:
            records = db.execute("""
                WITH compact AS (
                    SELECT id AS job_id, created, rowid AS ordinal,
                        json_extract(body,'$.trial_id') AS trial_id,
                        json_extract(body,'$.run_id') AS run_id,
                        json_extract(body,'$.state') AS state,
                        json_extract(body,'$.error') AS error
                    FROM jobs WHERE json_extract(body,'$.experiment_id')=?
                ), ranked AS (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY trial_id ORDER BY created DESC,ordinal DESC) AS position,
                        COUNT(*) OVER (PARTITION BY trial_id) AS attempt_count FROM compact
                )
                SELECT j.trial_id,j.job_id,j.run_id,j.state,j.error,j.attempt_count,r.sha256
                FROM ranked j LEFT JOIN runs r ON r.id=j.run_id WHERE j.position=1
            """, (experiment_id,)).fetchall()
        fields = ("trial_id", "job_id", "run_id", "state", "error", "attempt_count", "artifact_sha256")
        return {row[0]: dict(zip(fields, row, strict=True)) for row in records}

    def register(self, manifest: dict[str, Any], *, resume: bool) -> float:
        eid = manifest["experiment_id"]
        with self.repository.connect() as db:
            existing = db.execute("SELECT manifest,elapsed FROM experiments WHERE id=?", (eid,)).fetchone()
            if existing and not resume:
                raise ValueError("Experiment already exists; use resume or a distinct manifest")
            if existing and digest(json.loads(existing[0])) != digest(manifest):
                raise ValueError("Stored manifest differs from requested manifest")
            elapsed = existing[1] if existing else 0.0
            db.execute("INSERT OR IGNORE INTO experiments(id,manifest) VALUES(?,?)", (eid, encode(manifest).decode()))
        return float(elapsed)

    def update(self, experiment_id: str, state: str, elapsed: float) -> None:
        with self.repository.connect() as db:
            cursor = db.execute("UPDATE experiments SET state=?,elapsed=? WHERE id=?", (state, elapsed, experiment_id))
            if cursor.rowcount != 1:
                raise KeyError(experiment_id)
