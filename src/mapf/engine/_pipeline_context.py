"""Shared tick state and the local conflict boundary between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from mapf.core.components import SimFrame
from mapf.core.models import Conflict, Point
from mapf.core.protocols import AgentProtocol
from mapf.engine.contracts import TickWorld


@dataclass
class PipelineContext:
    """Mutable state belonging to one complete discrete simulation tick."""

    world: TickWorld
    current_time: int
    active_agents: dict[str, AgentProtocol]
    disappear_at_target: bool
    allow_wait: bool
    conflicts: list[Conflict] = field(default_factory=list)
    signed_contracts: list[dict[str, Any]] = field(default_factory=list)
    desired_moves: dict[str, Point] = field(default_factory=dict)
    resolved_moves: dict[str, Point] = field(default_factory=dict)
    is_unsolvable: bool = False
    all_done: bool = False
    frame: SimFrame | None = None


class SimulationStage(Protocol):
    """A stage may update tick state through the explicit world contract."""

    name: str

    def execute(self, ctx: PipelineContext) -> None: ...


def active_conflicts(ctx: PipelineContext, radius: int) -> list[Conflict]:
    config = ctx.world.config
    horizon = (
        min(
            config.negotiation_horizon or config.fov_size,
            config.broadcast_horizon or config.fov_size,
        )
        - 1
    )
    conflicts = ctx.world.detect_conflicts(
        paths={aid: a.planned_path for aid, a in ctx.world.agents.items()},
        goals={aid: a.target_pos for aid, a in ctx.world.agents.items()},
        current_time=ctx.current_time,
        lookahead_steps=horizon,
        disappear_at_target=ctx.disappear_at_target,
    )
    return [c for c in conflicts if _within_local_roster(ctx, c, radius)]


def _within_local_roster(ctx: PipelineContext, conflict: Conflict, radius: int) -> bool:
    if (
        conflict.agent_a not in ctx.active_agents
        or conflict.agent_b not in ctx.active_agents
    ):
        return False
    first = ctx.world.agents[conflict.agent_a].current_pos
    second = ctx.world.agents[conflict.agent_b].current_pos
    return max(abs(first.x - second.x), abs(first.y - second.y)) <= radius
