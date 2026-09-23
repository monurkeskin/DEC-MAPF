"""Frame capture and periodic replay keyframes after a completed joint move."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mapf.agents.base import goal_reached
from mapf.core.components import SimFrame
from mapf.core.models import RecordingLevel
from mapf.core.protocols import AgentProtocol
from mapf.engine._pipeline_context import PipelineContext
from mapf.telemetry.events import KeyframeEvent


@dataclass
class _FrameRoster:
    positions: dict[str, tuple[int, int]]
    targets: dict[str, tuple[int, int]]
    tokens: dict[str, int]
    paths: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    commitments: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def capture(
        cls, agents: dict[str, AgentProtocol], full_trace: bool
    ) -> _FrameRoster:
        roster = cls(
            {aid: (a.current_pos.x, a.current_pos.y) for aid, a in agents.items()},
            {aid: (a.target_pos.x, a.target_pos.y) for aid, a in agents.items()},
            {aid: a.tokens for aid, a in agents.items()},
        )
        if full_trace:
            roster.paths = {
                aid: [(p.x, p.y) for p in a.planned_path.points]
                for aid, a in agents.items()
            }
            roster.commitments = {
                aid: a.get_state().metadata.get("commitments", [])
                for aid, a in agents.items()
            }
        return roster


class PostUpdateStage:
    """Audit arrivals, capture the completed frame, and advance the tick."""

    name = "PostUpdate"

    def execute(self, ctx: PipelineContext) -> None:
        solved_count = sum(1 for a in ctx.world.agents.values() if goal_reached(a))
        active_count = len(ctx.active_agents)
        full_trace = ctx.world.config.recording_level == RecordingLevel.FULL_TRACE
        heat_records, heat_omitted = ctx.world.drain_decision_heat()
        roster = _FrameRoster.capture(ctx.world.agents, full_trace)
        ctx.frame = SimFrame(
            tick=ctx.current_time,
            active_agent_count=active_count,
            solved_agent_count=solved_count,
            agent_positions=roster.positions,
            agent_targets=roster.targets,
            agent_tokens=roster.tokens,
            active_conflicts=[
                {
                    "a": c.agent_a,
                    "b": c.agent_b,
                    "time": c.time,
                    "type": c.conflict_type.value,
                }
                for c in ctx.conflicts
            ],
            signed_contracts=ctx.signed_contracts,
            is_unsolvable=ctx.is_unsolvable,
            planned_paths=roster.paths,
            commitments=roster.commitments,
            local_observations=ctx.world.observation_snapshot() if full_trace else {},
            local_heat=heat_records,
            local_heat_omitted=heat_omitted,
        )
        level = getattr(ctx.world.config, "recording_level", RecordingLevel.FULL_TRACE)
        ctx.world.finish_tick(ctx.frame)
        ctx.all_done = all(goal_reached(a) for a in ctx.world.agents.values())
        self._emit_keyframe(ctx, level)

    @staticmethod
    def _emit_keyframe(ctx: PipelineContext, level: RecordingLevel) -> None:
        if level not in (RecordingLevel.EVENTS, RecordingLevel.FULL_TRACE):
            return
        interval = getattr(ctx.world.config, "keyframe_interval", 25)
        if ctx.current_time % interval != 0 and not ctx.all_done:
            return
        ctx.world.telemetry_hook.on_keyframe(
            KeyframeEvent(
                tick=ctx.current_time,
                agent_states={
                    aid: _keyframe_state(a) for aid, a in ctx.world.agents.items()
                },
            )
        )


def _keyframe_state(agent: AgentProtocol) -> dict[str, Any]:
    return {
        "pos": [agent.current_pos.x, agent.current_pos.y],
        "target": [agent.target_pos.x, agent.target_pos.y],
        "tokens": agent.tokens,
        "reached_goal": goal_reached(agent),
        "remaining_dist": len(agent.planned_path.points),
    }
