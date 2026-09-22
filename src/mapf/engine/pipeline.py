"""Discrete 5-Stage Simulation Pipeline Schedule for MAPF Engine.

Inspired by Entity Component System (ECS) game-loop stages:
1. StagePreUpdate: Perception & spatial topology audit (handling permanent parked obstacles)
2. StageConflictDetection: Lookahead conflict detection and agent matchmaking
3. StageNegotiation: Bilateral bargaining referee and contract execution
4. StageMovement: Collision-free movement resolution (MovementResolver)
5. StagePostUpdate: Settlement, goal arrival checks, and SimFrame snapshot generation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from mapf.agents.base import goal_reached
from mapf.core.components import SimFrame
from mapf.core.models import Conflict, Path, Point, RecordingLevel
from mapf.core.protocols import AgentProtocol
from mapf.engine.contracts import TickWorld
from mapf.engine.movement import JointMoveFailure, MovementResolver
from mapf.telemetry.events import (
    AgentMoveEvent,
    BroadcastEvent,
    DiagnosticEvent,
    KeyframeEvent,
    NegotiationSessionEvent,
)


@dataclass
class PipelineContext:
    """Shared execution context passed through pipeline stages during a discrete tick."""

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
    """Protocol for discrete tick pipeline stages."""

    name: str

    def execute(self, ctx: PipelineContext) -> None:
        """Execute stage operations mutating pipeline context."""
        ...


class PreUpdateStage:
    """Perception, parked-obstacle detours, and recovery of incomplete plans."""

    name = "PreUpdate"

    def execute(self, ctx: PipelineContext) -> None:
        if ctx.is_unsolvable or not ctx.active_agents:
            return

        local_views = {aid: ctx.world.for_agent(aid) for aid in ctx.active_agents}

        parked_positions = {
            a.target_pos for a in ctx.world.agents.values() if goal_reached(a)
        } if not ctx.disappear_at_target else set()
        for agent in ctx.active_agents.values():
            observed_parked = parked_positions & local_views[agent.agent_id].get_fov_obstacles(
                agent.current_pos, ctx.world.config.fov_size
            )
            blocking_obs = set(agent.planned_path.points) & observed_parked
            incomplete_plan = agent.planned_path.points[-1] != agent.target_pos
            if not blocking_obs and not incomplete_plan:
                continue
            from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar

            planner = SpaceTimeAStar(
                grid_width=ctx.world.config.grid_width,
                grid_height=ctx.world.config.grid_height,
                obstacles=ctx.world.config.obstacles | observed_parked,
            )
            reservations = ReservationTable()
            reserve = getattr(agent, "reserve_commitments", None)
            if callable(reserve):
                reserve(reservations, ctx.current_time)
            detour = planner.search(
                start=agent.current_pos,
                goal=agent.target_pos,
                start_time=ctx.current_time,
                reservation_table=reservations,
                allow_wait=ctx.allow_wait,
                max_time_steps=max(0, ctx.world.config.max_steps - ctx.current_time),
                permanent_at_goal=not ctx.disappear_at_target,
                max_expansions=ctx.world.config.max_astar_expansions,
            )
            if detour is not None:
                agent.apply_planned_path(detour)
                ctx.world.record_replan("solved")
            else:
                from mapf.core.geometry import grid_index

                geometry = grid_index(planner.width, planner.height,
                                      frozenset((p.x, p.y) for p in planner.obstacles))
                start = (agent.current_pos.x, agent.current_pos.y)
                goal = (agent.target_pos.x, agent.target_pos.y)
                reachable = start in geometry.components and (
                    geometry.components[start] == geometry.components.get(goal)
                )
                receipt = {
                    "agent_id": agent.agent_id,
                    "search_status": planner.last_search_status,
                    "expansions": planner.last_expansions,
                    "static_reachable": reachable,
                    "blocking_parked_cells": len(blocking_obs),
                    "terminal": not reachable,
                }
                ctx.world.record_replan(planner.last_search_status, receipt)
                ctx.world.telemetry_hook.on_diagnostic(DiagnosticEvent(
                    "REPLAN", ctx.current_time, receipt
                ))
                if not reachable:
                    # Includes an already truncated one-cell plan: it need not
                    # itself contain the parked obstacle to be disconnected.
                    # This certifies only the observed current static topology.
                    ctx.is_unsolvable = True
                    ctx.world.mark_unsolvable()
                    return
                if blocking_obs:
                    # A temporary reservation/search bound must not abort the
                    # world. Discard the now-blocked route, then retry next tick.
                    agent.apply_planned_path(Path(points=[agent.current_pos]))
            # A transient failed fallback leaves a safe partial plan, not an
            # absorbing non-goal state. Retry next tick with current reservations
            # and the remaining declared search/step budgets, even without peers.


class ConflictDetectionStage:
    """Stage 2: Discrete lookahead conflict detection and agent pair matchmaking."""

    name = "ConflictDetection"

    def execute(self, ctx: PipelineContext) -> None:
        if ctx.is_unsolvable or not ctx.active_agents:
            return

        planned_paths = {a_id: a.planned_path for a_id, a in ctx.world.agents.items()}
        all_conflicts = ctx.world.detect_conflicts(
            paths=planned_paths,
            goals={aid: agent.target_pos for aid, agent in ctx.world.agents.items()},
            current_time=ctx.current_time,
            lookahead_steps=min(ctx.world.config.negotiation_horizon or ctx.world.config.fov_size,
                                ctx.world.config.broadcast_horizon or ctx.world.config.fov_size) - 1,
            disappear_at_target=ctx.disappear_at_target,
        )
        radius = ctx.world.config.fov_size // 2
        ctx.conflicts = [
            c
            for c in all_conflicts
            if c.agent_a in ctx.active_agents
            and c.agent_b in ctx.active_agents
            and max(
                abs(
                    ctx.world.agents[c.agent_a].current_pos.x
                    - ctx.world.agents[c.agent_b].current_pos.x
                ),
                abs(
                    ctx.world.agents[c.agent_a].current_pos.y
                    - ctx.world.agents[c.agent_b].current_pos.y
                ),
            )
            <= radius
        ]


class NegotiationStage:
    """Stage 3: Bilateral referee, alternating offer bargaining, and detour formulation."""

    name = "Negotiation"

    def execute(self, ctx: PipelineContext) -> None:
        if ctx.is_unsolvable or not ctx.active_agents:
            return

        max_passes = ctx.world.config.verification_pass_limit
        radius = ctx.world.config.fov_size // 2
        for pass_idx in range(max_passes):
            # A completed synchronous session releases its lock. Keep disjoint
            # pairs within this snapshot; the next pass observes updated plans.
            busy_agents: set[str] = set()
            active_conflicts = self._active_conflicts(ctx, radius)
            if not active_conflicts:
                break

            # Modern deterministic order; the published repetitions randomized partners.
            active_conflicts.sort(
                key=lambda c: (
                    c.time,
                    min(c.agent_a, c.agent_b),
                    max(c.agent_a, c.agent_b),
                )
            )

            any_contract = False
            for c in active_conflicts:
                # Skip stale same-pass pairings involving an already changed plan.
                if c.agent_a in busy_agents or c.agent_b in busy_agents:
                    continue

                agent_a = ctx.world.agents[c.agent_a]
                agent_b = ctx.world.agents[c.agent_b]

                contract = ctx.world.negotiator.negotiate(
                    agent_a=agent_a,
                    agent_b=agent_b,
                    conflict=c,
                    env=ctx.world,
                    current_time=ctx.current_time,
                )
                busy_agents.add(c.agent_a)
                busy_agents.add(c.agent_b)

                if contract is not None:
                    any_contract = True
                    ctx.signed_contracts.append(
                        {
                            "time": ctx.current_time,
                            "agent_a": c.agent_a,
                            "agent_b": c.agent_b,
                            "location": [c.location_a.x, c.location_a.y],
                            "details": {
                                "session_id": contract.session_id,
                                "token_transfer_a_to_b": contract.token_transfer,
                                "accepted_by": contract.accepted_by,
                                "protocol_version": contract.protocol_version,
                                "allocated_path": [[p.x, p.y] for p in contract.allocated_path.points]
                                if contract.allocated_path is not None else None,
                                "conflict_end_tick": contract.conflict_tick,
                                "token_usage": contract.token_usage,
                                "settlement": getattr(ctx.world.negotiator, "last_settlement", None),
                                "path_a": [[p.x, p.y] for p in contract.path_a.points],
                                "path_b": [[p.x, p.y] for p in contract.path_b.points],
                                "absolute_start_tick": ctx.current_time,
                                "reservations_a": agent_a.get_state().metadata.get(
                                    "commitments", []
                                ),
                                "reservations_b": agent_b.get_state().metadata.get(
                                    "commitments", []
                                ),
                            },
                        }
                    )

                ctx.world.record_negotiation(
                    {
                        "time": ctx.current_time,
                        "agent_a": c.agent_a,
                        "agent_b": c.agent_b,
                        "success": contract is not None,
                        "location": c.location_a,
                        "wall_seconds": getattr(ctx.world.negotiator, "last_session_duration_sec", None),
                        "deadline_seconds": ctx.world.config.negotiation_deadline_sec,
                    }
                )

                reason = getattr(ctx.world.negotiator, "last_session_reason", "NONE")
                ctx.world.record_negotiation_outcome(reason)
                sess_id = getattr(ctx.world.negotiator, "last_session_id", "") or (
                    contract.session_id
                    if contract is not None
                    else f"nego-{ctx.current_time}-{c.agent_a}-{c.agent_b}"
                )
                total_rounds = getattr(ctx.world.negotiator, "last_session_rounds", 1)
                ctx.world.telemetry_hook.on_negotiation_end(
                    NegotiationSessionEvent(
                        session_id=sess_id,
                        tick=ctx.current_time,
                        initiator_id=c.agent_a,
                        opponent_id=c.agent_b,
                        conflict_x=c.location_a.x,
                        conflict_y=c.location_a.y,
                        total_rounds=total_rounds,
                        outcome="AGREED" if contract is not None else "FAILED",
                        tokens_transferred=abs(contract.token_transfer)
                        if contract is not None
                        else 0,
                        reject_reason=reason,
                    )
                )
                if reason == "NEGOTIATION_DEADLINE":
                    self._stop(ctx, "negotiation_deadline", {"session_id": sess_id,
                        "rounds": total_rounds, "pass": pass_idx + 1,
                        "diagnostics": getattr(ctx.world.negotiator, "last_diagnostics", {})})
                    return

            if not any_contract:
                break

    @staticmethod
    def _stop(ctx: PipelineContext, reason: str, detail: dict[str, Any]) -> None:
        ctx.is_unsolvable = True
        ctx.world.stop_negotiation(reason, detail)

    @staticmethod
    def _active_conflicts(ctx: PipelineContext, radius: int) -> list[Conflict]:
        conflicts = ctx.world.detect_conflicts(
            paths={aid: a.planned_path for aid, a in ctx.world.agents.items()},
            goals={aid: a.target_pos for aid, a in ctx.world.agents.items()},
            current_time=ctx.current_time,
            lookahead_steps=min(ctx.world.config.negotiation_horizon or ctx.world.config.fov_size,
                                ctx.world.config.broadcast_horizon or ctx.world.config.fov_size) - 1,
            disappear_at_target=ctx.disappear_at_target,
        )
        return [c for c in conflicts
                if c.agent_a in ctx.active_agents and c.agent_b in ctx.active_agents
                and max(abs(ctx.world.agents[c.agent_a].current_pos.x - ctx.world.agents[c.agent_b].current_pos.x),
                        abs(ctx.world.agents[c.agent_a].current_pos.y - ctx.world.agents[c.agent_b].current_pos.y)) <= radius]


class MovementStage:
    """Stage 4: Deterministic collision-free movement resolution and execution."""

    name = "Movement"

    def execute(self, ctx: PipelineContext) -> None:
        if ctx.is_unsolvable or not ctx.active_agents:
            return

        # 1. Collect desired moves from planned paths
        desired: dict[str, Point] = {}
        for a_id, agent in ctx.active_agents.items():
            if len(agent.planned_path.points) > 1:
                desired[a_id] = agent.planned_path.points[1]
            else:
                desired[a_id] = agent.planned_path.points[0]
            ctx.world.telemetry_hook.on_broadcast(
                BroadcastEvent(
                    tick=ctx.current_time,
                    agent_id=a_id,
                    fov_size=getattr(agent, "fov_size", 5),
                    cells_broadcasted=min(len(agent.planned_path.points), ctx.world.config.broadcast_horizon or ctx.world.config.fov_size),
                )
            )
        ctx.desired_moves = desired

        # 2. Collect permanently occupied cells (Settings 1 & 2)
        occupied_permanent: dict[Point, str] = {}
        if not ctx.disappear_at_target:
            for a_id, a in ctx.world.agents.items():
                if goal_reached(a):
                    occupied_permanent[a.target_pos] = a_id

        # 3. Resolve movements with MovementResolver
        diagnostics: dict[str, Any] = {}
        try:
            resolved = MovementResolver.resolve_step(
                active_agents=ctx.active_agents,
                desired_moves=desired,
                occupied_permanent=occupied_permanent,
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
            repair = diagnostics["joint_repair"]
            ctx.world.record_movement_repair(repair)
        if ctx.is_unsolvable:
            return  # Atomic: no agent moved and no simulated tick elapsed.
        ctx.resolved_moves = resolved
        ctx.world.record_motion(stationary=all(
            resolved[aid] == a.current_pos for aid, a in ctx.active_agents.items()))

        # Capture every fallback view before any physical position changes.
        # Otherwise later agents would observe a mixture of ticks t and t+1.
        movement_views = {aid: ctx.world.for_agent(aid) for aid in ctx.active_agents}
        # 4. Apply movements to agents
        for a_id, agent in ctx.active_agents.items():
            nxt = resolved[a_id]
            prev_pos = agent.current_pos
            if nxt != desired[a_id]:
                ctx.world.record_safety_intervention()
                ctx.world.telemetry_hook.on_diagnostic(DiagnosticEvent("SAFETY", ctx.current_time, {
                    "agent_id": a_id, "desired": [desired[a_id].x, desired[a_id].y],
                    "actual": [nxt.x, nxt.y], "reason": "joint_movement_conflict",
                    "semantic_violation": not ctx.allow_wait and nxt == prev_pos,
                }))
                new_pos = agent.force_move(nxt, movement_views[a_id], ctx.current_time)
                ctx.world.record_position(a_id, new_pos)
            else:
                new_pos = agent.step(ctx.current_time)
                ctx.world.record_position(a_id, new_pos)

            ctx.world.telemetry_hook.on_move(
                AgentMoveEvent(
                    tick=ctx.current_time,
                    agent_id=a_id,
                    x=new_pos.x,
                    y=new_pos.y,
                    is_waiting=(new_pos == prev_pos),
                    remaining_dist=max(0, len(agent.planned_path.points) - 1),
                )
            )


class PostUpdateStage:
    """Stage 5: Goal arrival audit, SimFrame snapshot creation, and tick advancement."""

    name = "PostUpdate"

    def execute(self, ctx: PipelineContext) -> None:
        solved_count = sum(
            1 for a in ctx.world.agents.values() if goal_reached(a)
        )
        active_count = len(ctx.active_agents)
        full_trace = ctx.world.config.recording_level == RecordingLevel.FULL_TRACE
        heat_records, heat_omitted = ctx.world.drain_decision_heat()

        # Build SimFrame snapshot
        ctx.frame = SimFrame(
            tick=ctx.current_time,
            active_agent_count=active_count,
            solved_agent_count=solved_count,
            agent_positions={
                aid: (a.current_pos.x, a.current_pos.y)
                for aid, a in ctx.world.agents.items()
            },
            agent_targets={
                aid: (a.target_pos.x, a.target_pos.y)
                for aid, a in ctx.world.agents.items()
            },
            agent_tokens={aid: a.tokens for aid, a in ctx.world.agents.items()},
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
            planned_paths={
                aid: [(p.x, p.y) for p in agent.planned_path.points]
                for aid, agent in ctx.world.agents.items()
            }
            if full_trace
            else {},
            commitments={
                aid: agent.get_state().metadata.get("commitments", [])
                for aid, agent in ctx.world.agents.items()
            }
            if full_trace
            else {},
            local_observations=ctx.world.observation_snapshot() if full_trace else {},
            local_heat=heat_records,
            local_heat_omitted=heat_omitted,
        )
        rec_level = getattr(
            ctx.world.config, "recording_level", RecordingLevel.FULL_TRACE
        )
        ctx.world.finish_tick(ctx.frame)
        ctx.all_done = all(
            goal_reached(a) for a in ctx.world.agents.values()
        )

        # Periodic full-state keyframe snapshot for instant back-trace seeking
        interval = getattr(ctx.world.config, "keyframe_interval", 25)
        if rec_level in (RecordingLevel.EVENTS, RecordingLevel.FULL_TRACE) and (
            ctx.current_time % interval == 0 or ctx.all_done
        ):
            agent_states = {
                aid: {
                    "pos": [a.current_pos.x, a.current_pos.y],
                    "target": [a.target_pos.x, a.target_pos.y],
                    "tokens": a.tokens,
                    "reached_goal": goal_reached(a),
                    "remaining_dist": len(a.planned_path.points),
                }
                for aid, a in ctx.world.agents.items()
            }
            ctx.world.telemetry_hook.on_keyframe(
                KeyframeEvent(
                    tick=ctx.current_time,
                    agent_states=agent_states,
                )
            )


class SimulationPipeline:
    """Orchestrates ordered execution of discrete tick pipeline stages."""

    def __init__(self, stages: list[SimulationStage] | None = None) -> None:
        self.stages = stages or [
            PreUpdateStage(),
            ConflictDetectionStage(),
            NegotiationStage(),
            MovementStage(),
            PostUpdateStage(),
        ]

    def step(self, ctx: PipelineContext) -> bool:
        """Execute one complete discrete tick through all stages."""
        for stage in self.stages:
            stage.execute(ctx)
            if ctx.is_unsolvable:
                return False
        return ctx.all_done
