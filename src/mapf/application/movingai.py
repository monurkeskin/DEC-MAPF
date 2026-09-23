"""Validate uploaded MovingAI files and build a provenance-bearing snapshot."""

from __future__ import annotations

import hashlib
from typing import Any

from mapf.application.contracts import MovingAIImport, ScenarioValidateRequest
from mapf.application.plans import scenario_snapshot
from mapf.core.models import Point
from mapf.core.movingai import ScenarioRow, parse_movingai_map, parse_movingai_rows


def movingai_snapshot(request: MovingAIImport) -> dict[str, Any]:
    """Share core parsing rules; apply workspace bounds before persisting anything."""
    grid = parse_movingai_map(request.map_text)
    width, height, _ = grid
    if width > 64 or height > 64:
        raise ValueError("MovingAI map dimensions exceed the 64 by 64 workspace limit")
    rows = parse_movingai_rows(request.scenario_text)
    _validate_map_references(rows, width, height)
    if len(rows) < request.agent_count:
        raise ValueError("Select enough agents from one map reference")
    selected = rows[: request.agent_count]
    snapshot = scenario_snapshot(_workspace_scenario(request, grid, selected))
    snapshot["source"] = {
        "format": "MovingAI",
        "map_sha256": hashlib.sha256(request.map_text.encode()).hexdigest(),
        "scenario_sha256": hashlib.sha256(request.scenario_text.encode()).hexdigest(),
        "selection": f"first {request.agent_count} rows; no random subsample",
    }
    return snapshot


def _workspace_scenario(
    request: MovingAIImport,
    grid: tuple[int, int, set[Point]],
    selected: list[ScenarioRow],
) -> ScenarioValidateRequest:
    """Convert the admitted ordered rows to the shared workspace contract."""
    width, height, obstacles = grid
    return ScenarioValidateRequest(
        grid_width=width,
        grid_height=height,
        setting=request.setting,
        name=request.name,
        starts={
            f"agent_{i}": (row.start.x, row.start.y) for i, row in enumerate(selected)
        },
        goals={
            f"agent_{i}": (row.goal.x, row.goal.y) for i, row in enumerate(selected)
        },
        obstacles=[(point.x, point.y) for point in obstacles],
    )


def _validate_map_references(rows: list[ScenarioRow], width: int, height: int) -> None:
    """Apply upload policy to parsed records, without a second text parser."""
    if any(row.dimensions != (width, height) for row in rows):
        raise ValueError("Scenario row references incompatible map dimensions")
    if len({row.map_name for row in rows}) != 1:
        raise ValueError("Select enough agents from one map reference")
