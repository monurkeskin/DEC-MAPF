"""Atomic joint-move resolution followed by execution against frozen local views."""

from __future__ import annotations

from typing import Any

from mapf.agents.base import goal_reached
from mapf.core.models import Point
from mapf.core.observations import LocalEnvironment
from mapf.engine._pipeline_context import PipelineContext
from mapf.engine.movement import JointMoveFailure, MovementResolver
from mapf.telemetry.events import AgentMoveEvent, BroadcastEvent, DiagnosticEvent


class MovementStage:
    """Resolve every move before any physical position changes."""

    name = "Movement"

    def execute(self, ctx: PipelineContext) -> None:
        if ctx.is_unsolvable or not ctx.active_agents:
            return
        ctx.desired_moves = self._desired_moves(ctx)
        resolved = self._resolve(ctx)
        if ctx.is_unsolvable:
            return  # No agent moved and no simulated tick elapsed.
        ctx.resolved_moves = resolved
        ctx.world.record_motion(
            stationary=all(
                resolved[aid] == a.current_pos for aid, a in ctx.active_agents.items()
            )
        )
        # Later agents must not observe a mixture of ticks t and t+1.
        views = {aid: ctx.world.for_agent(aid) for aid in ctx.active_agents}
        for aid in ctx.active_agents:
            self._apply_move(ctx, aid, views[aid])

    @staticmethod
    def _desired_moves(ctx: PipelineContext) -> dict[str, Point]:
        desired = {}
        for aid, agent in ctx.active_agents.items():
            points = agent.planned_path.points
            desired[aid] = points[1] if len(points) > 1 else points[0]
            ctx.world.telemetry_hook.on_broadcast(
                BroadcastEvent(
                    tick=ctx.current_time,
                    agent_id=aid,
                    fov_size=getattr(agent, "fov_size", 5),
                    cells_broadcasted=min(
                        len(points),
                        ctx.world.config.broadcast_horizon or ctx.world.config.fov_size,
                    ),
                )
            )
        return desired

    @staticmethod
    def _parked_occupants(ctx: PipelineContext) -> dict[Point, str]:
        if ctx.disappear_at_target:
            return {}
        return {
            a.target_pos: aid for aid, a in ctx.world.agents.items() if goal_reached(a)
        }

    def _resolve(self, ctx: PipelineContext) -> dict[str, Point]:
        occupied = self._parked_occupants(ctx)
        diagnostics: dict[str, Any] = {}
        try:
            resolved = MovementResolver.resolve_step(
                active_agents=ctx.active_agents,
                desired_moves=ctx.desired_moves,
                occupied_permanent=occupied,
                allow_wait=ctx.allow_wait,
                env=ctx.world,
                current_time=ctx.current_time,
                diagnostics=diagnostics,
            )
        except JointMoveFailure as failure:
            ctx.is_unsolvable = True
            ctx.world.stop_movement(failure.reason, failure.receipt)
            resolved = {}
        if "joint_repair" in diagnostics:
            ctx.world.record_movement_repair(diagnostics["joint_repair"])
        return resolved

    def _apply_move(
        self, ctx: PipelineContext, aid: str, view: LocalEnvironment
    ) -> None:
        agent = ctx.active_agents[aid]
        nxt, previous = ctx.resolved_moves[aid], agent.current_pos
        if nxt != ctx.desired_moves[aid]:
            self._record_intervention(ctx, aid)
            position = agent.force_move(nxt, view, ctx.current_time)
        else:
            position = agent.step(ctx.current_time)
        ctx.world.record_position(aid, position)
        ctx.world.telemetry_hook.on_move(
            AgentMoveEvent(
                tick=ctx.current_time,
                agent_id=aid,
                x=position.x,
                y=position.y,
                is_waiting=(position == previous),
                remaining_dist=max(0, len(agent.planned_path.points) - 1),
            )
        )

    @staticmethod
    def _record_intervention(ctx: PipelineContext, aid: str) -> None:
        agent = ctx.active_agents[aid]
        desired, actual = ctx.desired_moves[aid], ctx.resolved_moves[aid]
        ctx.world.record_safety_intervention()
        ctx.world.telemetry_hook.on_diagnostic(
            DiagnosticEvent(
                "SAFETY",
                ctx.current_time,
                {
                    "agent_id": aid,
                    "desired": [desired.x, desired.y],
                    "actual": [actual.x, actual.y],
                    "reason": "joint_movement_conflict",
                    "semantic_violation": not ctx.allow_wait
                    and actual == agent.current_pos,
                },
            )
        )
