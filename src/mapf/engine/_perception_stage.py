"""Local perception, bounded detours, and conflict detection before negotiation."""

from __future__ import annotations

from mapf.agents.base import goal_reached
from mapf.core.geometry import grid_index
from mapf.core.models import Path, Point
from mapf.core.protocols import AgentProtocol
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar
from mapf.engine._pipeline_context import PipelineContext, active_conflicts
from mapf.telemetry.events import DiagnosticEvent


class PreUpdateStage:
    """Perception, parked-obstacle detours, and recovery of incomplete plans."""

    name = "PreUpdate"

    def execute(self, ctx: PipelineContext) -> None:
        if ctx.is_unsolvable or not ctx.active_agents:
            return
        # Freeze every recipient view before any plan is revised.
        views = {aid: ctx.world.for_agent(aid) for aid in ctx.active_agents}
        parked = self._parked_positions(ctx)
        for agent in ctx.active_agents.values():
            observed = parked & views[agent.agent_id].get_fov_obstacles(
                agent.current_pos, ctx.world.config.fov_size
            )
            blocked = set(agent.planned_path.points) & observed
            incomplete = agent.planned_path.points[-1] != agent.target_pos
            if blocked or incomplete:
                self._replan(ctx, agent, observed, len(blocked))
                if ctx.is_unsolvable:
                    return

    @staticmethod
    def _parked_positions(ctx: PipelineContext) -> set[Point]:
        if ctx.disappear_at_target:
            return set()
        return {a.target_pos for a in ctx.world.agents.values() if goal_reached(a)}

    def _replan(
        self,
        ctx: PipelineContext,
        agent: AgentProtocol,
        observed_parked: set[Point],
        blocking_cells: int,
    ) -> None:
        planner = SpaceTimeAStar(
            grid_width=ctx.world.config.grid_width,
            grid_height=ctx.world.config.grid_height,
            obstacles=ctx.world.config.obstacles | observed_parked,
        )
        detour = self._search_detour(ctx, agent, planner)
        if detour is not None:
            agent.apply_planned_path(detour)
            ctx.world.record_replan("solved")
            return
        reachable = self._record_failed_detour(ctx, agent, planner, blocking_cells)
        if not reachable:
            # This only certifies disconnection in the observed static topology.
            ctx.is_unsolvable = True
            ctx.world.mark_unsolvable()
        elif blocking_cells:
            # A bounded search or temporary reservation must not abort the world.
            # Retry the safe partial plan next tick with current reservations.
            agent.apply_planned_path(Path(points=[agent.current_pos]))

    @staticmethod
    def _search_detour(
        ctx: PipelineContext,
        agent: AgentProtocol,
        planner: SpaceTimeAStar,
    ) -> Path | None:
        reservations = ReservationTable()
        reserve = getattr(agent, "reserve_commitments", None)
        if callable(reserve):
            reserve(reservations, ctx.current_time)
        return planner.search(
            start=agent.current_pos,
            goal=agent.target_pos,
            start_time=ctx.current_time,
            reservation_table=reservations,
            allow_wait=ctx.allow_wait,
            max_time_steps=max(0, ctx.world.config.max_steps - ctx.current_time),
            permanent_at_goal=not ctx.disappear_at_target,
            max_expansions=ctx.world.config.max_astar_expansions,
        )

    @staticmethod
    def _record_failed_detour(
        ctx: PipelineContext,
        agent: AgentProtocol,
        planner: SpaceTimeAStar,
        blocking_cells: int,
    ) -> bool:
        geometry = grid_index(
            planner.width,
            planner.height,
            frozenset((p.x, p.y) for p in planner.obstacles),
        )
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
            "blocking_parked_cells": blocking_cells,
            "terminal": not reachable,
        }
        ctx.world.record_replan(planner.last_search_status, receipt)
        ctx.world.telemetry_hook.on_diagnostic(
            DiagnosticEvent("REPLAN", ctx.current_time, receipt)
        )
        return reachable


class ConflictDetectionStage:
    """Find conflicts between active agents within their shared local field of view."""

    name = "ConflictDetection"

    def execute(self, ctx: PipelineContext) -> None:
        if ctx.is_unsolvable or not ctx.active_agents:
            return
        ctx.conflicts = active_conflicts(ctx, ctx.world.config.fov_size // 2)
