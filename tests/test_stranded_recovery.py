"""Transient planning failures must not create an absorbing non-goal state."""

from itertools import pairwise

import pytest

from mapf.agents.path_aware import PathAwareAgent
from mapf.core.commitments import CommitmentReservation
from mapf.core.models import Path, Point, SimulationConfig, SimulationSetting
from mapf.engine.pipeline import PipelineContext, PreUpdateStage
from mapf.engine.world import WorldSimulation


@pytest.mark.parametrize(
    "setting", [SimulationSetting.SETTING_2, SimulationSetting.SETTING_4]
)
def test_expired_transient_reservation_recovers_without_a_new_conflict(setting):
    world = WorldSimulation(
        SimulationConfig(grid_width=5, grid_height=3, setting=setting, max_steps=12)
    )
    agent = PathAwareAgent("a", Point(0, 1), Point(4, 1))
    world.add_agent(agent)
    world.initialize()
    # A held move at t=0 cannot replan from an occupied start at t=1.
    agent._commitments["temporary"] = CommitmentReservation(
        "temporary", "a", "peer", 1, (Point(0, 1),), "SC"
    )
    agent.force_move(Point(0, 1), world.for_agent("a"), 0)
    assert agent.planned_path.points == (Point(0, 1),)
    world._current_time = 1  # The physical held move has completed.
    world._path_history["a"].append(Point(0, 1))
    # No other agent/conflict can accidentally trigger negotiation-based recovery.
    for _ in range(8):
        if world.step():
            break
    assert agent.current_pos == agent.target_pos
    assert agent.reached_goal and not agent._commitments
    points = world._path_history["a"]
    assert all(abs(a.x - b.x) + abs(a.y - b.y) <= 1 for a, b in pairwise(points))


def test_recovery_uses_current_tick_and_retains_unexpired_reservations():
    world = WorldSimulation(
        SimulationConfig(
            grid_width=4,
            grid_height=3,
            setting=SimulationSetting.SETTING_4,
            max_steps=10,
        )
    )
    agent = PathAwareAgent("a", Point(0, 1), Point(3, 1))
    world.add_agent(agent)
    world.initialize()
    agent.apply_planned_path(Path(points=[Point(0, 1)]))
    record = CommitmentReservation("active", "a", "peer", 3, (Point(1, 1),), "SC")
    agent._commitments["active"] = record
    world._current_time = 2
    ctx = PipelineContext(world, 2, {"a": agent}, True, True)
    PreUpdateStage().execute(ctx)
    assert agent.current_pos == Point(0, 1)  # Planning does not move the agent.
    assert agent.planned_path.points[-1] == Point(3, 1)
    assert agent.planned_path.points[1] != Point(1, 1)  # The next move is at t=3.
    assert agent._commitments["active"] == record


def test_failed_recovery_is_bounded_and_does_not_invent_a_path_or_goal():
    world = WorldSimulation(
        SimulationConfig(
            grid_width=5,
            grid_height=3,
            setting=SimulationSetting.SETTING_4,
            obstacles={Point(1, y) for y in range(3)},
            max_steps=10,
            max_astar_expansions=100,
        )
    )
    agent = PathAwareAgent("a", Point(0, 1), Point(4, 1))
    world.add_agent(agent)
    world.initialize()
    for _ in range(3):
        assert not world.step()
    assert world.current_time == 0  # Static disconnection stops before movement.
    assert world._last_replan_failure["terminal"] is True
    assert agent.planned_path.points == (Point(0, 1),)
    assert not agent.reached_goal and agent.tokens == 5


def test_parked_obstacle_detour_preserves_both_live_commitments():
    world = WorldSimulation(
        SimulationConfig(
            grid_width=4,
            grid_height=3,
            setting=SimulationSetting.SETTING_2,
            max_steps=12,
        )
    )
    a = PathAwareAgent("a", Point(0, 1), Point(3, 1))
    parked = PathAwareAgent("parked", Point(1, 1), Point(1, 1))
    world.add_agent(a)
    world.add_agent(parked)
    world.initialize()
    for peer, point in [("upper", Point(0, 0)), ("lower", Point(0, 2))]:
        a._commitments[peer] = CommitmentReservation(peer, "a", peer, 1, (point,), "SC")
    PreUpdateStage().execute(PipelineContext(world, 0, {"a": a}, False, True))
    assert a.planned_path.points[-1] == a.target_pos
    assert a.planned_path.points[1] == Point(0, 1)
    assert Point(1, 1) not in a.planned_path.points


def test_transient_reserved_start_during_parked_detour_does_not_abort_world():
    world = WorldSimulation(SimulationConfig(
        grid_width=4, grid_height=3, setting=SimulationSetting.SETTING_2, max_steps=12,
    ))
    a = PathAwareAgent("a", Point(0, 1), Point(3, 1))
    parked = PathAwareAgent("parked", Point(1, 1), Point(1, 1))
    world.add_agent(a)
    world.add_agent(parked)
    world.initialize()
    # A reachable safety fallback can occupy a reserved start; that finite
    # obligation expires at this tick. The static detour around parked is open.
    a._commitments["temporary"] = CommitmentReservation(
        "temporary", "a", "peer", 0, (Point(0, 1),), "SC"
    )
    world.step()
    assert not world._is_unsolvable
    for _ in range(10):
        if world.step():
            break
    assert a.reached_goal
    assert Point(1, 1) not in world._path_history["a"]
