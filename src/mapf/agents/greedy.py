from __future__ import annotations

from mapf.agents.base import BaseAgent
from mapf.core.models import (
    Bid,
    Conflict,
)
from mapf.core.obstacle_memory import planning_obstacles
from mapf.core.protocols import EnvironmentProtocol


class GreedyAgent(BaseAgent):
    """Prefer the current path and reject voluntary concessions.

    TAOP-v2 can still require a feasible concession when a repeated offer is
    unaffordable; that rule belongs to the session, not this strategy."""

    def on_pre_negotiation(
        self,
        opponent_id: str,
        conflict: Conflict,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> None:
        pass

    def make_bid(
        self,
        opponent_id: str,
        last_opponent_bid: Bid | None,
        env: EnvironmentProtocol,
        current_time: int,
        round_num: int,
    ) -> Bid:
        return Bid(
            bidder_id=self._agent_id,
            proposed_path=self._planned_path,
            token_offered=0,
            round_num=round_num,
        )

    def evaluate_bid(
        self,
        bid: Bid,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> bool:
        return False


class ConcederAgent(BaseAgent):
    """Accept an offer when local replanning finds a feasible alternative."""

    def on_pre_negotiation(
        self,
        opponent_id: str,
        conflict: Conflict,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> None:
        pass

    def make_bid(
        self,
        opponent_id: str,
        last_opponent_bid: Bid | None,
        env: EnvironmentProtocol,
        current_time: int,
        round_num: int,
    ) -> Bid:
        token_offer = min(1, self._current_tokens)
        return Bid(
            bidder_id=self._agent_id,
            proposed_path=self._planned_path,
            token_offered=token_offer,
            round_num=round_num,
        )

    def evaluate_bid(
        self,
        bid: Bid,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> bool:
        from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar

        local_obs = planning_obstacles(env, self._current_pos, env.config.fov_size)
        planner = SpaceTimeAStar(
            grid_width=env.config.grid_width,
            grid_height=env.config.grid_height,
            obstacles=local_obs,
        )
        res_table = ReservationTable()
        self.reserve_commitments(res_table, current_time)
        res_table.reserve_path(
            agent_id=bid.bidder_id, path=bid.proposed_path, start_time=current_time
        )

        detour = planner.search(
            start=self._current_pos,
            goal=self._target_pos,
            start_time=current_time,
            reservation_table=res_table,
            allow_wait=env.config.setting.allow_wait,
            max_expansions=env.config.max_astar_expansions,
            max_time_steps=max(0, env.config.max_steps - (current_time)),
            permanent_at_goal=not env.config.setting.disappear_at_target,
        )
        if detour is not None:
            self._planned_path = detour
            return True
        return False
