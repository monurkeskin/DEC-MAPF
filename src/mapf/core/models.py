from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Point(BaseModel):
    """2D Grid coordinate with immutable value semantics."""
    model_config = ConfigDict(frozen=True)

    x: int = Field(strict=True)
    y: int = Field(strict=True)

    def __init__(self, x: int = 0, y: int = 0, **kwargs: Any) -> None:
        if "x" in kwargs:
            x = kwargs.pop("x")
        if "y" in kwargs:
            y = kwargs.pop("y")
        super().__init__(x=x, y=y, **kwargs)

    def manhattan_distance(self, other: Point) -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)

    def get_neighbors(self, allow_wait: bool = True) -> list[Point]:
        """4-connected grid neighbors + optional wait action."""
        neighbors = [
            Point(x=self.x + 1, y=self.y),
            Point(x=self.x - 1, y=self.y),
            Point(x=self.x, y=self.y + 1),
            Point(x=self.x, y=self.y - 1),
        ]
        if allow_wait:
            neighbors.append(Point(x=self.x, y=self.y))
        return neighbors

    def __str__(self) -> str:
        return f"({self.x},{self.y})"


class Path(BaseModel):
    """Discrete time sequence of points representing an agent trajectory."""
    model_config = ConfigDict(frozen=True)

    points: tuple[Point, ...] = ()

    def __init__(self, points: Sequence[Point] = (), **kwargs: Any) -> None:
        super().__init__(points=points, **kwargs)

    @property
    def length(self) -> int:
        """Action cost (number of transitions); 0 for a stationary single-point path."""
        return max(0, len(self.points) - 1)

    def at_time(self, t: int, disappear_at_target: bool = False) -> Point | None:
        """Returns position at timestep t."""
        if t < 0:
            return None
        if t < len(self.points):
            return self.points[t]
        if disappear_at_target:
            return None
        # In non-disappear settings, agent stays at goal forever
        return self.points[-1] if self.points else None

    def slice_from(self, t: int) -> Path:
        """Returns remaining path starting from timestep t."""
        if t >= len(self.points):
            return Path(points=[self.points[-1]] if self.points else [])
        return Path(points=self.points[t:])


class ConflictType(str, Enum):
    VERTEX = "VERTEX"
    EDGE = "EDGE"


class Conflict(BaseModel):
    """Represents a conflict between two agents in space-time."""
    model_config = ConfigDict(frozen=True)

    agent_a: str
    agent_b: str
    time: int
    conflict_type: ConflictType
    location_a: Point
    location_b: Point | None = None  # Relevant for edge swap conflicts

    @property
    def end_time(self) -> int:
        """Inclusive conflict state: an edge at t finishes at t+1."""
        return self.time + int(self.conflict_type == ConflictType.EDGE)


class ActionType(str, Enum):
    OFFER = "OFFER"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class Bid(BaseModel):
    """A negotiation bid proposing a path commitment and token exchange."""
    model_config = ConfigDict(frozen=True)

    bidder_id: str
    proposed_path: Path
    token_offered: int = Field(default=0, ge=0)
    round_num: int = 0


class Contract(BaseModel):
    """Formal agreed contract between negotiating agents."""
    model_config = ConfigDict(frozen=True)

    session_id: str
    agent_a: str
    agent_b: str
    path_a: Path
    path_b: Path
    token_transfer: int = 0  # Tokens paid from A to B (positive if A pays B)
    timestamp: int = 0
    accepted_by: str | None = None  # None identifies legacy bilateral reservations
    allocated_path: Path | None = None
    conflict_tick: int | None = None  # Inclusive conflict end state (edge arrival, not departure)
    token_usage: dict[str, int] = Field(default_factory=dict)
    protocol_version: str = "legacy-alternating-v1"


class BidDecision(BaseModel):
    """A proposal value; constructing/evaluating one cannot commit an agent state."""
    model_config = ConfigDict(frozen=True)
    accepted: bool
    proposed_path: Path
    reason: str
    components: dict[str, Any] = Field(default_factory=dict)


class SimulationSetting(int, Enum):
    """JAAMAS 2024 defined four problem settings."""
    SETTING_1 = 1  # Disappear=False, Wait=False
    SETTING_2 = 2  # Disappear=False, Wait=True
    SETTING_3 = 3  # Disappear=True,  Wait=False
    SETTING_4 = 4  # Disappear=True,  Wait=True

    @property
    def disappear_at_target(self) -> bool:
        return self in (SimulationSetting.SETTING_3, SimulationSetting.SETTING_4)

    @property
    def allow_wait(self) -> bool:
        return self in (SimulationSetting.SETTING_2, SimulationSetting.SETTING_4)


class CommitmentType(str, Enum):
    """JAAMAS 2024 Section 5.1 commitment types."""
    STANDARD = "SC"  # Standard / Full commitment to entire agreed path
    DYNAMIC = "DC"   # Dynamic commitment up to the conflicted timestep
    ZERO = "ZC"      # May decommit on new conflicts after the agreement tick's movement


class RecordingLevel(str, Enum):
    """Granularity of simulation logging and telemetry capture (L09)."""
    METRICS_ONLY = "metrics-only"
    EVENTS = "events"
    FULL_TRACE = "full-trace"


class SimulationConfig(BaseModel):
    """Global parameters for MAPF simulation runs."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    grid_width: int = 16
    grid_height: int = 16
    obstacles: set[Point] = Field(default_factory=set)
    fov_size: int = Field(default=5, ge=3)
    broadcast_horizon: int | None = Field(default=None, ge=1)
    negotiation_horizon: int | None = Field(default=None, ge=1)
    negotiation_protocol: Literal["taop-v2", "taop-v1", "legacy-alternating-v1"] = "taop-v2"
    setting: SimulationSetting = SimulationSetting.SETTING_4
    commitment_type: CommitmentType = CommitmentType.STANDARD
    initial_tokens: int = Field(default=5, ge=0)
    max_steps: int = 200
    random_seed: int = 42
    centralized_timeout_sec: float = Field(default=60.0, ge=0.00001)
    negotiation_round_limit: int = Field(default=30, ge=1)
    negotiation_deadline_sec: float | None = Field(default=60.0, gt=0)
    negotiation_lifecycle_hook: Any = Field(default=None, exclude=True)
    verification_pass_limit: int = Field(default=5, ge=1)
    max_astar_expansions: int = Field(default=1500, ge=100)
    enable_telemetry: bool = False
    telemetry_hook: Any = None
    keyframe_interval: int = Field(default=25, ge=1)
    recording_level: RecordingLevel = RecordingLevel.FULL_TRACE
    heat_recording_limit: int = Field(default=250000, ge=0, le=2000000)


class AgentState(BaseModel):
    """Runtime snapshot of an agent."""
    agent_id: str
    current_pos: Point
    target_pos: Point
    current_tokens: int
    initial_tokens: int
    initial_path_length: int
    remaining_path: Path
    reached_goal: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
