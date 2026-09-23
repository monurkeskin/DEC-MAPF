"""Immutable delivered information; strategy views contain no world/agent reference."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from mapf.core.models import Path, Point, SimulationConfig
from mapf.core.space_time_grid import CandidateSearchCache


@dataclass(frozen=True, slots=True)
class Message:
    sender: str
    recipient: str
    tick: int
    points: tuple[tuple[int, int], ...]
    kind: Literal["BROADCAST", "OFFER"] = "BROADCAST"
    session_id: str | None = None
    acknowledgement: int = 0

    def _payload(self) -> dict[str, Any]:
        # All fields are immutable values. asdict() recursively deep-copied each
        # coordinate for every measured delivery, despite JSON only reading them.
        return {"sender": self.sender, "recipient": self.recipient, "tick": self.tick,
                "points": self.points, "kind": self.kind, "session_id": self.session_id,
                "acknowledgement": self.acknowledgement}

    def to_dict(self) -> dict[str, Any]:
        return {"event_type": "MESSAGE", **self._payload(), "payload_bytes": self.payload_bytes}

    @property
    def payload_bytes(self) -> int:
        return len(json.dumps(self._payload(), sort_keys=True, separators=(",", ":")).encode())


@dataclass(frozen=True, slots=True)
class Observation:
    agent_id: str
    tick: int
    position: Point
    obstacles: frozenset[Point]
    messages: tuple[Message, ...]
    remembered_obstacles: frozenset[Point] = frozenset()

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id, "tick": self.tick,
            "position": [self.position.x, self.position.y],
            "obstacles": [[p.x, p.y] for p in sorted(self.obstacles, key=lambda p: (p.y, p.x))],
            "remembered_obstacles": [[p.x, p.y] for p in sorted(self.remembered_obstacles, key=lambda p: (p.y, p.x))],
            "messages": [m.to_dict() for m in self.messages],
        }


class LocalEnvironment:
    """Static map, current observation and recipient memory, with no global queries."""

    def __init__(self, config: SimulationConfig, observation: Observation) -> None:
        self.config = config.model_copy(update={"telemetry_hook": None, "negotiation_lifecycle_hook": None,
                                                "native_diagnostics_hook": None,
                                                "obstacles": set(config.obstacles)})
        self.observation = observation
        self.candidate_cache = CandidateSearchCache()

    def is_obstacle(self, p: Point) -> bool:
        return p in self.config.obstacles or p in self.observation.obstacles or p in self.remembered_obstacles

    @property
    def remembered_obstacles(self) -> frozenset[Point]:
        return self.observation.remembered_obstacles

    def is_within_bounds(self, p: Point) -> bool:
        return 0 <= p.x < self.config.grid_width and 0 <= p.y < self.config.grid_height

    def get_fov_obstacles(self, center: Point, fov_size: int) -> set[Point]:
        radius = fov_size // 2
        return {p for p in self.observation.obstacles
                if abs(p.x - center.x) <= radius and abs(p.y - center.y) <= radius}

    def get_fov_broadcasts(self, center: Point, fov_size: int, requesting_agent_id: str) -> dict[str, Path]:
        if requesting_agent_id != self.observation.agent_id:
            raise ValueError("An agent cannot inspect another recipient's observation")
        return {m.sender: Path(points=[Point(x, y) for x, y in m.points])
                for m in self.observation.messages if m.kind == "BROADCAST"}
