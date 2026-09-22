from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mapf.core.models import Path, Point


@dataclass(slots=True)
class SpatialComponent:
    """Component managing an agent's 2D grid spatial state and target."""

    current_pos: Point
    target_pos: Point
    reached_goal: bool = False
    priority: int = 0

    @property
    def distance_to_goal(self) -> int:
        return self.current_pos.manhattan_distance(self.target_pos)


@dataclass(slots=True)
class PathPlanningComponent:
    """Component managing planned trajectories, history, and space-time commitments."""

    planned_path: Path = field(default_factory=lambda: Path(points=[]))
    initial_path_length: int = 0
    commitments: dict[int, Point] = field(default_factory=dict)
    unroutable_obs_count: int = 0

    def prune_commitments(self, current_time: int) -> None:
        """Discard expired space-time commitments."""
        self.commitments = {
            t: pt for t, pt in self.commitments.items() if t > current_time
        }


@dataclass(slots=True)
class NegotiationComponent:
    """Component managing token endowment, strategy type, and negotiation state."""

    tokens: int = 5
    strategy: str = "PathAware"
    concessions: int = 0
    deals_completed: int = 0
    total_negotiations: int = 0

    def adjust_tokens(self, delta: int) -> None:
        if self.tokens + delta < 0:
            raise ValueError("Token adjustment would overdraw the agent balance")
        self.tokens += delta


@dataclass(slots=True, frozen=True)
class SimFrame:
    """Lightweight immutable snapshot of a single discrete simulation tick.

    Used for headless streaming, GUI scrubbing, and post-hoc trajectory analysis.
    """

    tick: int
    active_agent_count: int
    solved_agent_count: int
    agent_positions: dict[str, tuple[int, int]]
    agent_targets: dict[str, tuple[int, int]]
    agent_tokens: dict[str, int]
    active_conflicts: list[dict[str, Any]] = field(default_factory=list)
    signed_contracts: list[dict[str, Any]] = field(default_factory=list)
    is_unsolvable: bool = False
    planned_paths: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    commitments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    local_observations: dict[str, Any] = field(default_factory=dict)
    local_heat: list[dict[str, Any]] = field(default_factory=list)
    local_heat_omitted: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "active_agents": self.active_agent_count,
            "solved_agents": self.solved_agent_count,
            "positions": {aid: list(pos) for aid, pos in self.agent_positions.items()},
            "targets": {aid: list(pos) for aid, pos in self.agent_targets.items()},
            "tokens": self.agent_tokens,
            "conflicts": self.active_conflicts,
            "contracts": self.signed_contracts,
            "is_unsolvable": self.is_unsolvable,
            "planned_paths": self.planned_paths,
            "commitments": self.commitments,
            "local_observations": self.local_observations,
            "local_heat": self.local_heat,
            "local_heat_omitted": self.local_heat_omitted,
        }
