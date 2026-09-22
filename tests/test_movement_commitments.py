"""Executed safety moves must obey live obligations, not only physical occupancy."""

import pytest

from mapf.agents.path_aware import PathAwareAgent
from mapf.core.commitments import CommitmentReservation
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.engine.movement import MovementResolver
from mapf.engine.world import WorldSimulation


@pytest.mark.parametrize('allow_wait', [True, False])
def test_collision_fallback_does_not_enter_a_live_reservation(allow_wait):
    world = WorldSimulation(SimulationConfig(grid_width=3, grid_height=3))
    a = PathAwareAgent('a', Point(0, 1), Point(2, 1), initial_tokens=10)
    b = PathAwareAgent('b', Point(2, 1), Point(0, 1), initial_tokens=1)
    # Wait-enabled greedy resolution holds b; no-wait resolution sidesteps up.
    forbidden = Point(2, 1) if allow_wait else Point(2, 0)
    b._commitments['live'] = CommitmentReservation('live', 'b', 'peer', 8, (forbidden,), 'SC')
    result = MovementResolver.resolve_step({'a': a, 'b': b}, {'a': Point(1, 1), 'b': Point(1, 1)},
        {}, allow_wait, world, current_time=7)
    assert result['b'] != forbidden
    assert len(set(result.values())) == 2
    assert b.current_pos == Point(2, 1)  # Resolution is pure; movement is separate.
    assert b._commitments['live'].end_tick == 8


@pytest.mark.parametrize('setting', [SimulationSetting.SETTING_1, SimulationSetting.SETTING_2])
def test_parking_does_not_break_a_future_goal_reservation(setting):
    world = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2, setting=setting))
    agent = PathAwareAgent('a', Point(0, 0), Point(1, 0))
    agent._commitments['future'] = CommitmentReservation('future', 'a', 'peer', 3, (Point(1, 0),), 'SC')
    result = MovementResolver.resolve_step({'a': agent}, {'a': Point(1, 0)}, {}, setting.allow_wait, world)
    assert result['a'] != agent.target_pos


def test_disappearance_does_not_reserve_future_goal_occupancy():
    world = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2, setting=SimulationSetting.SETTING_4))
    agent = PathAwareAgent('a', Point(0, 0), Point(1, 0))
    agent._commitments['future'] = CommitmentReservation('future', 'a', 'peer', 3, (Point(1, 0),), 'SC')
    result = MovementResolver.resolve_step({'a': agent}, {'a': Point(1, 0)}, {}, True, world)
    assert result['a'] == agent.target_pos


@pytest.mark.parametrize("protocol,reason", [
    ("taop-v1", "movement_constraints_infeasible"),
    ("taop-v2", "negotiation_deadline"),
])
def test_no_legal_joint_move_stops_before_forbidden_wait_is_executed(protocol, reason):
    world = WorldSimulation(SimulationConfig(grid_width=2, grid_height=1,
        setting=SimulationSetting.SETTING_3, max_steps=10,
        negotiation_protocol=protocol, negotiation_deadline_sec=.02))
    world.add_agent(PathAwareAgent('a', Point(0, 0), Point(1, 0)))
    world.add_agent(PathAwareAgent('b', Point(1, 0), Point(0, 0)))
    result = world.run()
    assert result['total_steps'] == 0
    assert result['path_history'] == {'a': [Point(0, 0)], 'b': [Point(1, 0)]}
    assert not result['success']
    assert result['termination_reason'] == reason
