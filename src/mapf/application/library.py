"""Bounded saved-run read model, independent of artifact replay and execution."""
from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mapf.application.runs import RunRepository, check_id, digest, encode


class _Cursor(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: Literal[1] = 1
    created: float
    run_id: str
    snapshot_rowid: int = Field(ge=0)
    filters: str


class RunLibrary:
    def __init__(self, repository: RunRepository) -> None:
        self.repository = repository

    def page(self, *, limit: int = 50, cursor: str | None = None,
             solver_name: str | None = None, validation_status: str | None = None,
             experiment_id: str | None = None) -> dict[str, Any]:
        filters = {"solver_name": solver_name or None, "validation_status": validation_status or None,
                   "experiment_id": experiment_id or None}
        _check_page_inputs(limit, filters)
        signature = digest(filters)
        previous = _decode_cursor(cursor, signature)
        with self.repository.connect() as db:
            snapshot = previous.snapshot_rowid if previous else db.execute("SELECT COALESCE(MAX(rowid),0) FROM runs").fetchone()[0]
            query = _LibraryQuery(snapshot, filters)
            records, total = query.read(db, limit, previous)
            solvers, statuses = _facets(db)
        selected = records[:limit]
        next_cursor = _next_cursor(records, limit, snapshot, signature)
        return {"items": [dict(json.loads(row[2]), pinned=bool(row[3])) for row in selected],
                "total": total, "next_cursor": next_cursor, "solver_names": solvers,
                "validation_statuses": statuses}


def _check_page_inputs(limit: int, filters: dict[str, str | None]) -> None:
    if not 1 <= limit <= 100:
        raise ValueError("Library page size must be 1 to 100")
    if any(len(value or "") > 160 for value in filters.values()):
        raise ValueError("Library filter exceeds 160 characters")


def _facets(db: sqlite3.Connection) -> tuple[list[str], list[str]]:
    solvers = [r[0] for r in db.execute("SELECT DISTINCT json_extract(summary,'$.solver_name') FROM runs ORDER BY 1")]
    statuses = [r[0] for r in db.execute("SELECT DISTINCT json_extract(summary,'$.validation_status') FROM runs ORDER BY 1")]
    return solvers, statuses


def _decode_cursor(cursor: str | None, signature: str) -> _Cursor | None:
    previous = None
    if cursor:
        try:
            if len(cursor) > 1024:
                raise ValueError("Cursor is too long")
            previous = _Cursor.model_validate_json(base64.b64decode(cursor, altchars=b"-_", validate=True))
            check_id(previous.run_id)
        except (ValueError, ValidationError, binascii.Error) as exc:
            raise ValueError("Invalid library cursor") from exc
        if previous.filters != signature:
            raise ValueError("Library cursor belongs to different filters; start a new page")
    return previous


@dataclass(frozen=True)
class _LibraryQuery:
    snapshot: int
    filters: dict[str, str | None]

    def selection(self) -> tuple[str, list[Any]]:
        where = ["r.rowid <= ?"]
        args: list[Any] = [self.snapshot]
        for field in ("solver_name", "validation_status"):
            if self.filters[field]:
                where.append(f"json_extract(r.summary,'$.{field}')=?")
                args.append(self.filters[field])
        if self.filters["experiment_id"]:
            where.append("EXISTS (SELECT 1 FROM jobs j WHERE json_extract(j.body,'$.run_id')=r.id "
                         "AND json_extract(j.body,'$.experiment_id')=?)")
            args.append(self.filters["experiment_id"])
        return " AND ".join(where), args

    def read(self, db: sqlite3.Connection, limit: int, previous: _Cursor | None) -> tuple[list[Any], int]:
        condition, args = self.selection()
        total = db.execute("SELECT count(*) FROM runs r WHERE " + condition, args).fetchone()[0]
        if previous:
            condition += " AND (r.created < ? OR (r.created=? AND r.id < ?))"
            args.extend([previous.created, previous.created, previous.run_id])
        records = db.execute("SELECT r.id,r.created,r.summary,r.pinned FROM runs r WHERE " + condition
            + " ORDER BY r.created DESC,r.id DESC LIMIT ?", [*args, limit + 1]).fetchall()
        return records, total


def _next_cursor(records: list[Any], limit: int, snapshot: int, signature: str) -> str | None:
    if len(records) <= limit:
        return None
    last = records[limit - 1]
    cursor = _Cursor(created=last[1], run_id=last[0], snapshot_rowid=snapshot, filters=signature)
    return base64.urlsafe_b64encode(encode(cursor.model_dump())).decode()
