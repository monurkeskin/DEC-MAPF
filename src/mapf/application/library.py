"""Bounded saved-run read model, independent of artifact replay and execution."""
from __future__ import annotations

import base64
import binascii
import json
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
        if not 1 <= limit <= 100:
            raise ValueError("Library page size must be 1 to 100")
        filters = {"solver_name": solver_name or None, "validation_status": validation_status or None,
                   "experiment_id": experiment_id or None}
        if any(value is not None and len(value) > 160 for value in filters.values()):
            raise ValueError("Library filter exceeds 160 characters")
        signature = digest(filters)
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
        with self.repository.connect() as db:
            snapshot = previous.snapshot_rowid if previous else db.execute("SELECT COALESCE(MAX(rowid),0) FROM runs").fetchone()[0]
            where = ["r.rowid <= ?"]
            args: list[Any] = [snapshot]
            for field in ("solver_name", "validation_status"):
                if filters[field]:
                    where.append(f"json_extract(r.summary,'$.{field}')=?")
                    args.append(filters[field])
            if filters["experiment_id"]:
                where.append("EXISTS (SELECT 1 FROM jobs j WHERE json_extract(j.body,'$.run_id')=r.id "
                             "AND json_extract(j.body,'$.experiment_id')=?)")
                args.append(filters["experiment_id"])
            condition = " AND ".join(where)
            total = db.execute("SELECT count(*) FROM runs r WHERE " + condition, args).fetchone()[0]
            if previous:
                condition += " AND (r.created < ? OR (r.created=? AND r.id < ?))"
                args.extend([previous.created, previous.created, previous.run_id])
            records = db.execute("SELECT r.id,r.created,r.summary,r.pinned FROM runs r WHERE " + condition
                + " ORDER BY r.created DESC,r.id DESC LIMIT ?", [*args, limit + 1]).fetchall()
            solvers = [r[0] for r in db.execute("SELECT DISTINCT json_extract(summary,'$.solver_name') FROM runs ORDER BY 1")]
            statuses = [r[0] for r in db.execute("SELECT DISTINCT json_extract(summary,'$.validation_status') FROM runs ORDER BY 1")]
        selected = records[:limit]
        next_cursor = None
        if len(records) > limit:
            last = selected[-1]
            next_cursor = base64.urlsafe_b64encode(encode(_Cursor(created=last[1], run_id=last[0],
                snapshot_rowid=snapshot, filters=signature).model_dump())).decode()
        return {"items": [dict(json.loads(row[2]), pinned=bool(row[3])) for row in selected],
                "total": total, "next_cursor": next_cursor, "solver_names": solvers,
                "validation_statuses": statuses}
