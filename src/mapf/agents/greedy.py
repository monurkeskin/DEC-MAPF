from __future__ import annotations

from mapf.agents.base import BaseAgent
from mapf.core.models import (
    Bid,
    Conflict,
)
from mapf.core.protocols import EnvironmentProtocol


class GreedyAgent(BaseAgent):
    """GreedyAgent: Never concedes, always insists on its own shortest path."""

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
        # Always insist on own current planned path with 0 tokens offered
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
        # Only accept if opponent's bid causes zero delay to own plan
        return False


class ConcederAgent(BaseAgent):
    """ConcederAgent: Concedes immediately on first round if a feasible alternative exists."""

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
        # Conceder accepts opponent's path by replanning its own path around opponent
        from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar

        local_obs = env.config.obstacles | env.get_fov_obstacles(
            self._current_pos, env.config.fov_size
        )
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
