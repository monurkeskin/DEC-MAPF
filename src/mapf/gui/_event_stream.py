"""Resume and deliver a durable job journal using the SSE transport protocol."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import HTTPException, Request

from mapf.application.runs import TERMINAL, RunRepository


def replay_cursor(last_event_id: str | None, cursor: int, event_count: int) -> int:
    if last_event_id is not None:
        try:
            cursor = int(last_event_id)
        except ValueError as exc:
            raise HTTPException(
                422, "Last-Event-ID must be a nonnegative integer"
            ) from exc
        if cursor < 0:
            raise HTTPException(422, "Last-Event-ID must be nonnegative")
    if cursor > event_count:
        raise HTTPException(
            409, "Cursor is ahead of journal; reload authoritative state"
        )
    return cursor


async def journal_events(
    repo: RunRepository, job_id: str, request: Request, cursor: int
) -> AsyncIterator[str]:
    heartbeat_at = asyncio.get_running_loop().time()
    while not await request.is_disconnected():
        for event in repo.events(job_id, cursor):
            cursor = event["sequence"]
            yield f"id: {cursor}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
        current = repo.get_job(job_id)
        if current and current["state"] in TERMINAL and not repo.events(job_id, cursor):
            break
        now = asyncio.get_running_loop().time()
        if now - heartbeat_at >= 5:
            yield ": heartbeat\n\n"
            heartbeat_at = now
        await asyncio.sleep(0.1)
