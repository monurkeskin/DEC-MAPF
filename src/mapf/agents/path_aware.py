from __future__ import annotations

from typing import Any

from mapf.agents.base import BaseAgent
from mapf.core.models import (
    Bid,
    Conflict,
    Path,
    Point,
)
from mapf.core.obstacle_memory import planning_obstacles
from mapf.core.protocols import EnvironmentProtocol
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar


class PathAwareAgent(BaseAgent):
    """Choose concessions from the token balance and remaining path length."""

    def __init__(
        self,
        agent_id: str,
        start_pos: Point,
        target_pos: Point,
        initial_tokens: int = 5,
        commitment_type: Any = None,
    ) -> None:
        super().__init__(
            agent_id,
            start_pos,
            target_pos,
            initial_tokens,
            commitment_type=commitment_type,
        )
        self._active_conflict: Conflict | None = None
        self._alternative_paths: list[Path] = []

    def on_pre_negotiation(
        self,
        opponent_id: str,
        conflict: Conflict,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> None:
        self._active_conflict = conflict
        self._last_conflict_step = max(0, conflict.end_time - current_time)
        self._alternative_paths = self._generate_candidate_paths(
            env, current_time, conflict
        )

    def _generate_candidate_paths(
        self, env: EnvironmentProtocol, current_time: int, conflict: Conflict
    ) -> list[Path]:
        local_obs = planning_obstacles(env, self._current_pos, env.config.fov_size)
        planner = SpaceTimeAStar(
            grid_width=env.config.grid_width,
            grid_height=env.config.grid_height,
            obstacles=local_obs,
        )

        candidates: list[Path] = [self._planned_path]

        res_table = ReservationTable()
        opponent_id = (
            conflict.agent_b if conflict.agent_a == self._agent_id else conflict.agent_a
        )
        broadcasts = env.get_fov_broadcasts(
            self._current_pos, env.config.fov_size, self._agent_id
        )
        if opponent_id in broadcasts:
            res_table.reserve_path(
                agent_id=opponent_id,
                path=broadcasts[opponent_id],
                start_time=current_time,
            )
        else:
            res_table.reserve_vertex(
                agent_id=opponent_id,
                location=conflict.location_a,
                time=conflict.time,
            )

        self.reserve_commitments(res_table, current_time)

        detour_path = planner.search(
            start=self._current_pos,
            goal=self._target_pos,
            start_time=current_time,
            reservation_table=res_table,
            allow_wait=env.config.setting.allow_wait,
            max_expansions=env.config.max_astar_expansions,
            max_time_steps=max(0, env.config.max_steps - (current_time)),
            permanent_at_goal=not env.config.setting.disappear_at_target,
        )
        if detour_path is not None and detour_path != self._planned_path:
            candidates.append(detour_path)

        return candidates

    def make_bid(
        self,
        opponent_id: str,
        last_opponent_bid: Bid | None,
        env: EnvironmentProtocol,
        current_time: int,
        round_num: int,
    ) -> Bid:
        # Check concession rate with increasing token cost per insistence
        usage = getattr(self, "_acknowledged_usage", round_num)
        rate = self._calculate_concession_rate(token_cost=usage)

        if (rate < 1.0 or self._current_tokens < usage) and len(
            self._alternative_paths
        ) > 1:
            # CONCEDE: Offer alternative detour path or zero incentive
            chosen_path = self._alternative_paths[1]
            token_offer = 0
        else:
            # GREEDY: Insist on preferred primary path, offering escalating tokens
            chosen_path = self._planned_path
            token_offer = min(self._current_tokens, round_num)

        return Bid(
            bidder_id=self._agent_id,
            proposed_path=chosen_path,
            token_offered=token_offer,
            round_num=round_num,
        )

    def evaluate_bid(
        self,
        bid: Bid,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> bool:
        """Find a feasible detour, then apply the shared concession policy."""
        res_table = ReservationTable()
        res_table.reserve_path(
            agent_id=bid.bidder_id, path=bid.proposed_path, start_time=current_time
        )

        self.reserve_commitments(res_table, current_time)

        local_obs = planning_obstacles(env, self._current_pos, env.config.fov_size)
        planner = SpaceTimeAStar(
            grid_width=env.config.grid_width,
            grid_height=env.config.grid_height,
            obstacles=local_obs,
        )

        my_reconstructed_path = planner.search(
            start=self._current_pos,
            goal=self._target_pos,
            start_time=current_time,
            reservation_table=res_table,
            allow_wait=env.config.setting.allow_wait,
            max_expansions=env.config.max_astar_expansions,
            max_time_steps=max(0, env.config.max_steps - current_time),
            permanent_at_goal=not env.config.setting.disappear_at_target,
        )

        if my_reconstructed_path is None:
            self._last_decision = {"reason": "NO_FEASIBLE_RESPONSE", "feasible": False}
            return False

        reference = getattr(self, "_negotiation_reference_path", self._planned_path)
        delay = my_reconstructed_path.length - reference.length
        self._last_decision = {
            "candidate_actions": my_reconstructed_path.length,
            "reference_actions": reference.length,
            "delay": delay,
            "score": -float(my_reconstructed_path.length),
            "concession_rate": self._calculate_concession_rate(0),
            "feasible": True,
            "reason": "NON_WORSENING_RESPONSE" if delay <= 0 else "LONGER_RESPONSE",
        }
        return self._accept_response(
            my_reconstructed_path, bid, env.config.negotiation_protocol
        )
