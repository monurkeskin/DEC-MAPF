#!/usr/bin/env python3
"""Example 2: Custom Negotiation Agent.

Historical subclass sketch: initializes an agent but does not register or run it.
This is not a qualified TAOP-v2 strategy. In current sessions acknowledgement
usage is owned by the protocol ledger, not by a strategy's token_offered choice.
See docs/EXTENDING.md for current contracts and examples/04_supervised_study.py
for a runnable study with existing strategies.
"""
from mapf import BaseAgent
from mapf.core.models import Bid, Conflict, Point
from mapf.core.protocols import EnvironmentProtocol
from mapf.core.space_time_grid import SpaceTimeAStar


class StraightLineBiasAgent(BaseAgent):
    """Custom agent that penalizes trajectory turns during negotiation."""

    def on_pre_negotiation(
        self,
        opponent_id: str,
        conflict: Conflict,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> None:
        """Called immediately before entering a bilateral bargaining session."""

    def make_bid(
        self,
        opponent_id: str,
        last_opponent_bid: Bid | None,
        env: EnvironmentProtocol,
        current_time: int,
        round_num: int,
    ) -> Bid:
        """Generate bid offering a candidate path with turn-penalty preference."""
        astar = SpaceTimeAStar(
            grid_width=env.config.grid_width,
            grid_height=env.config.grid_height,
            obstacles=env.config.obstacles,
        )
        candidates = astar.find_bounded_candidate_paths(
            start=self._current_pos,
            goal=self._target_pos,
            reservation_table=self.reservation_table,
            time_step=current_time,
            allow_wait=env.config.setting.allow_wait,
            max_paths=5,
        )

        best_path = self._planned_path
        min_turns = float("inf")

        for p in candidates:
            # Count turns along the trajectory
            turns = 0
            for i in range(1, len(p.points) - 1):
                dx1 = p.points[i].x - p.points[i - 1].x
                dy1 = p.points[i].y - p.points[i - 1].y
                dx2 = p.points[i + 1].x - p.points[i].x
                dy2 = p.points[i + 1].y - p.points[i].y
                if (dx1, dy1) != (dx2, dy2):
                    turns += 1

            if turns < min_turns:
                min_turns = turns
                best_path = p

        return Bid(
            bidder_id=self._agent_id,
            proposed_path=best_path,
            token_offered=1 if round_num > 2 else 0,
            round_num=round_num,
        )

    def evaluate_bid(
        self,
        bid: Bid,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> bool:
        """Accept counter-bid if token offered is greater than zero."""
        return bid.token_offered > 0


def main() -> None:
    print("=" * 60)
    print("  Historical subclass initialization: StraightLineBiasAgent")
    print("=" * 60)

    # Instantiate agent
    agent = StraightLineBiasAgent(
        agent_id="Agent_01",
        start_pos=Point(0, 0),
        target_pos=Point(5, 5),
        initial_tokens=5,
    )

    print(f"Agent ID:       {agent.agent_id}")
    print(f"Start:          ({agent.current_pos.x}, {agent.current_pos.y})")
    print(f"Target:         ({agent.target_pos.x}, {agent.target_pos.y})")
    print(f"Token Balance:  {agent.tokens}")
    print("\nSuccessfully initialized custom negotiation agent subclass.")
    print("No negotiation was executed; this sketch is not a qualified TAOP-v2 policy.")
    print("=" * 60)


if __name__ == "__main__":
    main()
