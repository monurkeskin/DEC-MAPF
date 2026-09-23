"""Physical stopping conditions and independent solution validity are distinct."""

import pytest

from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.engine.world import WorldSimulation


def test_arrival_after_a_malformed_agent_hold_does_not_claim_a_step_limit():
    class FaultyAgent(PathAwareAgent):
        def step(self, current_time):
            # A strategy/plugin violates the authorized movement once. The
            # independent validator must still distinguish arrival from validity.
            return self.current_pos if current_time == 0 else super().step(current_time)
    world = WorldSimulation(
        SimulationConfig(
            grid_width=3,
            grid_height=3,
            setting=SimulationSetting.SETTING_3,
            max_steps=15,
        )
    )
    world.add_agent(FaultyAgent('a', Point(0, 0), Point(2, 0)))

    result = world.run()

    assert result["path_history"]['a'][:2] == [Point(0, 0), Point(0, 0)]
    assert result["total_steps"] == 3 < world.config.max_steps
    assert result["solved_count"] == result["total_agents"] == 1
    assert result["success"] is False
    assert result["termination_reason"] == "all_arrived"


@pytest.mark.parametrize(
    ("max_steps", "success", "reason"),
    [(1, False, "step_limit"), (8, True, "all_arrived")],
)
def test_real_step_limit_and_valid_arrival_remain_distinct(max_steps, success, reason):
    world = WorldSimulation(
        SimulationConfig(
            grid_width=3,
            grid_height=1,
            setting=SimulationSetting.SETTING_4,
            max_steps=max_steps,
        )
    )
    world.add_agent(PathAwareAgent("a", Point(0, 0), Point(2, 0)))
    result = world.run()
    assert result["success"] is success
    assert result["termination_reason"] == reason


def test_parked_obstacle_failure_does_not_claim_a_step_limit():
    world = WorldSimulation(
        SimulationConfig(
            grid_width=3,
            grid_height=1,
            setting=SimulationSetting.SETTING_2,
            max_steps=8,
        )
    )
    world.add_agent(PathAwareAgent("a", Point(0, 0), Point(2, 0)))
    world.add_agent(PathAwareAgent("parked", Point(1, 0), Point(1, 0)))
    result = world.run()
    assert result["total_steps"] == 0
    assert result["success"] is False
    assert result["termination_reason"] == "permanent_goal_disconnection"
    assert result["solver_diagnostics"]["last_reachability_failure"]["disconnected_agents"] == ["a"]
