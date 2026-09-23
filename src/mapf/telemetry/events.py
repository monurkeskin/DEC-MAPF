"""Typed simulation events for manifests, replay, negotiation and observations.

Frozen dataclasses prevent field reassignment; nested payloads can still be
mutable. The recording boundary snapshots them before asynchronous writing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    event_type: Literal[
        "TOKEN_TRANSFER",
        "SAFETY",
        "OBSERVATION",
        "MOVEMENT_REPAIR",
        "REPLAN",
        "REACHED_STATE",
        "NEGOTIATION_STOP",
        "DECISION_HEAT",
    ]
    tick: int
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {**self.details, "event_type": self.event_type, "tick": self.tick}


@dataclass(slots=True, frozen=True)
class ManifestEvent:
    """Record the source identity and selected configuration fields at startup."""

    git_commit: str
    random_seed: int
    grid_width: int
    grid_height: int
    agent_count: int
    setting: str
    commitment: str
    fov_size: int
    obstacles_count: int
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": "MANIFEST",
            "git_commit": self.git_commit,
            "random_seed": self.random_seed,
            "grid_width": self.grid_width,
            "grid_height": self.grid_height,
            "agent_count": self.agent_count,
            "setting": self.setting,
            "commitment": self.commitment,
            "fov_size": self.fov_size,
            "obstacles_count": self.obstacles_count,
            "timestamp": self.timestamp,
        }


@dataclass(slots=True, frozen=True)
class KeyframeEvent:
    """Periodic recorded agent state used to bound visual replay reconstruction.

    A keyframe is not a complete solver checkpoint or an exact-resume contract.
    """

    tick: int
    agent_states: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": "KEYFRAME",
            "tick": self.tick,
            "agent_states": self.agent_states,
        }


@dataclass(slots=True, frozen=True)
class AgentMoveEvent:
    """Emitted on every discrete simulation tick when an agent advances or waits."""

    tick: int
    agent_id: str
    x: int
    y: int
    is_waiting: bool
    remaining_dist: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": "MOVE",
            "tick": self.tick,
            "agent_id": self.agent_id,
            "x": self.x,
            "y": self.y,
            "is_waiting": self.is_waiting,
            "remaining_dist": self.remaining_dist,
        }


@dataclass(slots=True, frozen=True)
class OfferBidEvent:
    """Emitted for every individual bid, acceptance, or rejection in negotiation."""

    session_id: str
    tick: int
    round_idx: int
    agent_id: str
    path_length: int
    path_heat: float | None
    offered_utility: float | None
    decision: str = "OFFER"  # "OFFER", "ACCEPT", "REJECT"
    reject_reason: str = "NONE"  # "NONE", "INSUFFICIENT_UTILITY", "STATIONARY_IMPASSE"
    utility_components: dict[str, Any] = field(default_factory=dict)
    token_usage: int = 0
    repeated_offer: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": "BID",
            "session_id": self.session_id,
            "tick": self.tick,
            "round_idx": self.round_idx,
            "agent_id": self.agent_id,
            "path_length": self.path_length,
            "path_heat": self.path_heat,
            "offered_utility": self.offered_utility,
            "decision": self.decision,
            "reject_reason": self.reject_reason,
            "utility_components": self.utility_components,
            "token_usage": self.token_usage,
            "repeated_offer": self.repeated_offer,
        }


@dataclass(slots=True, frozen=True)
class NegotiationSessionEvent:
    """Emitted when a bilateral negotiation session concludes."""

    session_id: str
    tick: int
    initiator_id: str
    opponent_id: str
    conflict_x: int
    conflict_y: int
    total_rounds: int
    outcome: str  # "AGREED" or "FAILED"
    tokens_transferred: int
    reject_reason: str = "NONE"  # "NONE", "STATIONARY_IMPASSE", "MAX_ROUNDS_TIMEOUT", "INSUFFICIENT_TOKENS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": "NEGO_SESSION",
            "session_id": self.session_id,
            "tick": self.tick,
            "initiator_id": self.initiator_id,
            "opponent_id": self.opponent_id,
            "conflict_x": self.conflict_x,
            "conflict_y": self.conflict_y,
            "total_rounds": self.total_rounds,
            "outcome": self.outcome,
            "tokens_transferred": self.tokens_transferred,
            "reject_reason": self.reject_reason,
        }


@dataclass(slots=True, frozen=True)
class BroadcastEvent:
    """Record the sender-side path-length summary emitted before movement."""

    tick: int
    agent_id: str
    fov_size: int
    cells_broadcasted: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": "BROADCAST",
            "tick": self.tick,
            "agent_id": self.agent_id,
            "fov_size": self.fov_size,
            "cells_broadcasted": self.cells_broadcasted,
        }
