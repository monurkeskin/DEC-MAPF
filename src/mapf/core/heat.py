"""Actual decision fields and bounded recording; no retrospective reconstruction."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, FiniteFloat

from mapf.core.models import Point

Weight = Annotated[FiniteFloat, Field(ge=0)]


@dataclass(frozen=True)
class DecisionHeatValues:
    position: Point
    opponent_id: str | None
    fov_size: int
    aggregate: Mapping[Point, float]
    fields: tuple[Mapping[Point, float], ...]


class DecisionHeatRecord(BaseModel):
    record_id: str
    agent_id: str
    tick: int = Field(ge=0)
    session_id: str
    opponent_id: str | None
    position: list[int] = Field(min_length=2, max_length=2)
    fov_size: int
    source: Literal["actual_strategy_weights"] = "actual_strategy_weights"
    status: Literal["recorded", "budget_exhausted"]
    aggregate: dict[str, Weight] = Field(default_factory=dict)
    fields: list[dict[str, Weight]] = Field(default_factory=list)
    required_entries: int = Field(ge=0)
    recorded_entries: int = Field(ge=0)


class HeatRecorder:
    """At most a declared number of sparse values and 4096 decision headers/run.

    Frames drain per-tick records, avoiding repeated stale tensors. No provider
    is consulted unless full-trace recording is enabled.
    """

    def __init__(
        self, enabled: bool, entry_limit: int, record_limit: int = 4096
    ) -> None:
        self.enabled, self.entry_limit, self.record_limit = (
            enabled,
            entry_limit,
            record_limit,
        )
        self.entries = self.total = self.omitted = self.omitted_this_tick = 0
        self.records: list[dict[str, Any]] = []

    def capture(self, agent: Any, tick: int, session_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        provider = getattr(agent, "decision_heat_values", None)
        if not callable(provider):
            return None
        if self.total >= self.record_limit:
            self.omitted += 1
            self.omitted_this_tick += 1
            return None
        values = provider()
        if not isinstance(values, DecisionHeatValues):
            raise TypeError("A decision heat provider must return DecisionHeatValues")
        required = len(values.aggregate) + sum(len(field) for field in values.fields)
        admitted = self.entries + required <= self.entry_limit

        def sparse(field: Mapping[Point, float]) -> dict[str, float]:
            return {f"{point.x}-{point.y}": value for point, value in field.items()}

        self.total += 1
        record = DecisionHeatRecord(
            record_id=f"heat-{self.total}",
            agent_id=agent.agent_id,
            tick=tick,
            session_id=session_id,
            opponent_id=values.opponent_id,
            position=[values.position.x, values.position.y],
            fov_size=values.fov_size,
            status="recorded" if admitted else "budget_exhausted",
            aggregate=sparse(values.aggregate) if admitted else {},
            fields=[sparse(field) for field in values.fields] if admitted else [],
            required_entries=required,
            recorded_entries=required if admitted else 0,
        ).model_dump(mode="json")
        self.entries += record["recorded_entries"]
        if not admitted:
            self.omitted += 1
            self.omitted_this_tick += 1
        self.records.append(record)
        return record

    def drain(self) -> tuple[list[dict[str, Any]], int]:
        records, omitted = self.records, self.omitted_this_tick
        self.records, self.omitted_this_tick = [], 0
        return records, omitted
