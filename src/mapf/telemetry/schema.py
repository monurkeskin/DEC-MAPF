"""Versioned event normalization shared by disk and in-memory recorders."""
from __future__ import annotations

from typing import Any, Protocol

from mapf.core.heat import DecisionHeatRecord


class SerializableEvent(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


REQUIRED = {
    "MANIFEST": {"git_commit", "random_seed", "agent_count"},
    "MOVE": {"tick", "agent_id", "x", "y", "is_waiting"},
    "KEYFRAME": {"tick", "agent_states"},
    "BID": {"tick", "session_id", "round_idx", "agent_id", "decision"},
    "NEGO_SESSION": {"tick", "session_id", "outcome"},
    "BROADCAST": {"tick", "agent_id", "cells_broadcasted"},
    "MESSAGE": {"tick", "sender", "recipient", "points", "payload_bytes", "kind"},
    "TOKEN_TRANSFER": {"tick", "payer", "payee", "amount", "balances_before", "balances_after"},
    "SAFETY": {"tick", "agent_id", "reason"},
    "OBSERVATION": {"tick"},
    "MOVEMENT_REPAIR": {"tick", "node_limit", "search_nodes", "components", "remaining_holds"},
    "REPLAN": {"tick", "agent_id", "search_status", "expansions", "static_reachable", "terminal"},
    "REACHED_STATE": {"tick", "scope", "disconnected_agents", "parked_cells", "component_builds"},
    "NEGOTIATION_STOP": {"tick", "reason", "scope", "diagnostics"},
    "DECISION_HEAT": {"tick", "record_id", "agent_id", "session_id", "fields", "source", "status"},
}


def normalize(event: SerializableEvent, sequence: int) -> dict[str, Any]:
    value = event.to_dict()
    kind = value.get("event_type")
    if kind not in REQUIRED or REQUIRED[kind] - value.keys():
        raise ValueError(f"Malformed telemetry event: {kind}")
    value["schema_version"] = "telemetry-2"
    value["sequence"] = sequence
    value["phase"] = "post_move" if kind in ("MOVE", "KEYFRAME") else "pre_move"
    if value["phase"] == "post_move":
        value["tick"] += 1
    if kind == "MESSAGE":
        value["points"] = [list(p) for p in value["points"]]
    EVENT_ADAPTER.validate_python(value)
    return value

# Exported discriminated union for current events. Arbitrary policy component
# dictionaries remain explicit extension points; absent utility is JSON null.
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, allow_inf_nan=False)
    schema_version: Literal["telemetry-2"]
    sequence: int = Field(ge=1)
    phase: Literal["pre_move", "post_move"]
    run_id: str | None = None
    attempt_id: str | None = None
    source_sha256: str | None = None

class ManifestRecord(EventRecord):
    event_type: Literal["MANIFEST"]
    git_commit: str
    random_seed: int
    agent_count: int

class TickRecord(EventRecord):
    tick: int = Field(ge=0)

class MoveRecord(TickRecord):
    event_type: Literal["MOVE"]
    agent_id: str
    x: int
    y: int
    is_waiting: bool
    remaining_dist: int

class KeyframeRecord(TickRecord):
    event_type: Literal["KEYFRAME"]
    agent_states: dict[str, dict[str, Any]]

class BidRecord(TickRecord):
    event_type: Literal["BID"]
    session_id: str
    round_idx: int
    agent_id: str
    decision: str
    path_length: int
    path_heat: float | None
    offered_utility: float | None
    utility_components: dict[str, Any]
    token_usage: int
    repeated_offer: bool
    reject_reason: str

class SessionRecord(TickRecord):
    event_type: Literal["NEGO_SESSION"]
    session_id: str
    initiator_id: str
    opponent_id: str
    total_rounds: int
    outcome: Literal["AGREED", "FAILED"]
    tokens_transferred: int
    reject_reason: str

class BroadcastRecord(TickRecord):
    event_type: Literal["BROADCAST"]
    agent_id: str
    cells_broadcasted: int
    fov_size: int

class MessageRecord(TickRecord):
    event_type: Literal["MESSAGE"]
    sender: str
    recipient: str
    points: list[list[int]]
    payload_bytes: int
    kind: Literal["BROADCAST", "OFFER"]
    session_id: str | None
    acknowledgement: int

class TransferRecord(TickRecord):
    event_type: Literal["TOKEN_TRANSFER"]
    payer: str
    payee: str
    amount: int = Field(ge=0)
    balances_before: dict[str, int]
    balances_after: dict[str, int]

class SafetyRecord(TickRecord):
    event_type: Literal["SAFETY"]
    agent_id: str
    reason: str
    desired: list[int]
    actual: list[int]
    semantic_violation: bool

class ObservationRecord(TickRecord):
    event_type: Literal["OBSERVATION"]

class MovementRepairComponent(BaseModel):
    agents: list[str]
    status: Literal["repaired", "budget_exhausted", "immediate_infeasible", "progress_unavailable"]
    search_nodes: int = Field(ge=0)

class MovementRepairRecord(TickRecord):
    event_type: Literal["MOVEMENT_REPAIR"]
    cause: Literal["semantic", "progress"] = "semantic"
    node_limit: int = Field(ge=0)
    search_nodes: int = Field(ge=0)
    components: list[MovementRepairComponent]
    remaining_holds: list[str]
    remaining_blocked_agents: list[str] = Field(default_factory=list)

class ReplanRecord(TickRecord):
    event_type: Literal["REPLAN"]
    agent_id: str
    search_status: str
    expansions: int = Field(ge=0)
    static_reachable: bool
    blocking_parked_cells: int = Field(ge=0)
    terminal: bool

class ReachedStateRecord(TickRecord):
    event_type: Literal["REACHED_STATE"]
    scope: Literal["reached_state_only"]
    disconnected_agents: list[str] = Field(min_length=1)
    parked_cells: list[list[int]] = Field(min_length=1)
    component_builds: int = Field(ge=1)

class NegotiationStopRecord(TickRecord):
    event_type: Literal["NEGOTIATION_STOP"]
    reason: str
    scope: str
    diagnostics: dict[str, Any]

class DecisionHeatEventRecord(TickRecord, DecisionHeatRecord):
    event_type: Literal['DECISION_HEAT']


TelemetryRecord = Annotated[
    ManifestRecord | MoveRecord | KeyframeRecord | BidRecord | SessionRecord |
    BroadcastRecord | MessageRecord | TransferRecord | SafetyRecord | ObservationRecord |
    MovementRepairRecord | ReplanRecord | ReachedStateRecord | NegotiationStopRecord | DecisionHeatEventRecord,
    Field(discriminator="event_type"),
]
EVENT_ADAPTER: TypeAdapter[TelemetryRecord] = TypeAdapter(TelemetryRecord)

class TelemetryEnvelope(BaseModel):
    schema_version: Literal["telemetry-2"] = "telemetry-2"
    events: list[TelemetryRecord]
