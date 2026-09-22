"""Early stopping uses an irreversible physical condition, never a policy guess."""
from itertools import product
from unittest.mock import Mock

import pytest

from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.engine.world import WorldSimulation


@pytest.mark.parametrize('setting', [SimulationSetting.SETTING_1, SimulationSetting.SETTING_2])
def test_unseen_permanent_blocker_stops_without_changing_agent_information(setting):
    world = WorldSimulation(SimulationConfig(grid_width=7, grid_height=1,
        setting=setting, fov_size=3, max_steps=20))
    world.add_agent(PathAwareAgent('moving', Point(0, 0), Point(6, 0)))
    world.add_agent(PathAwareAgent('parked', Point(3, 0), Point(3, 0)))
    result = world.run()
    assert result['termination_reason'] == 'permanent_goal_disconnection'
    assert not result['success'] and result['total_steps'] == 0
    assert result['path_history']['moving'] == [Point(0, 0)]
    assert not world.for_agent('moving').is_obstacle(Point(3, 0))
    assert world.agents['moving'].tokens == 5
    witness = result['solver_diagnostics']['last_reachability_failure']
    assert witness['disconnected_agents'] == ['moving']
    assert witness['parked_cells'] == [[3, 0]]
    assert witness['scope'] == 'reached_state_only'


@pytest.mark.parametrize('setting', [SimulationSetting.SETTING_3, SimulationSetting.SETTING_4])
def test_disappearing_arrival_does_not_become_a_permanent_blocker(setting):
    world = WorldSimulation(SimulationConfig(grid_width=7, grid_height=1,
        setting=setting, fov_size=3, max_steps=20))
    world.add_agent(PathAwareAgent('moving', Point(0, 0), Point(6, 0)))
    world.add_agent(PathAwareAgent('arrived', Point(3, 0), Point(3, 0)))
    result = world.run()
    assert result['success'] and result['total_steps'] == 6
    assert result['solver_diagnostics']['last_reachability_failure'] is None


def test_new_arrival_invalidates_connectivity_before_another_pipeline_step():
    obstacles = {Point(x, 1) for x in range(7) if x != 3}
    world = WorldSimulation(SimulationConfig(grid_width=7, grid_height=2,
        obstacles=obstacles, setting=SimulationSetting.SETTING_2))
    a = PathAwareAgent('a', Point(0, 0), Point(6, 0))
    b = PathAwareAgent('b', Point(3, 1), Point(3, 0))
    world.add_agent(a); world.add_agent(b)
    pipeline = Mock(); pipeline.step.return_value = False
    world._pipeline = pipeline
    world.step()
    assert pipeline.step.call_count == 1 and world._stop_reason is None
    # Explicit legal first joint move. A target becomes unreachable at this state,
    # despite both starts being connected to their targets before the arrival.
    a._current_pos = Point(1, 0)
    b._current_pos = Point(3, 0); b._reached_goal = True
    world._path_history = {'a':[Point(0, 0), Point(1, 0)], 'b':[Point(3, 1), Point(3, 0)]}
    world._current_time = 1
    world.step()
    assert pipeline.step.call_count == 1
    assert world._stop_reason == 'permanent_goal_disconnection'
    assert world.current_time == 1 and a.current_pos == Point(1, 0)


def test_movable_agents_are_not_permanent_obstacles():
    world = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2,
        obstacles={Point(0, 1), Point(2, 1)}, setting=SimulationSetting.SETTING_2))
    world.add_agent(PathAwareAgent('a', Point(0, 0), Point(2, 0)))
    world.add_agent(PathAwareAgent('b', Point(1, 0), Point(1, 1)))
    pipeline = Mock(); pipeline.step.return_value = False; world._pipeline = pipeline
    world.step()
    assert pipeline.step.call_count == 1 and world._stop_reason is None


def test_reached_state_telemetry_preserves_the_pre_move_tick():
    from mapf.telemetry.hook import NullTelemetryHook
    from mapf.telemetry.schema import normalize

    class Collector(NullTelemetryHook):
        def __init__(self):
            self.events = []

        def on_diagnostic(self, event):
            self.events.append(normalize(event, len(self.events) + 1))

    collector = Collector()
    world = WorldSimulation(SimulationConfig(grid_width=7, grid_height=1,
        setting=SimulationSetting.SETTING_2, fov_size=3, max_steps=20,
        enable_telemetry=True, telemetry_hook=collector))
    world.add_agent(PathAwareAgent('moving', Point(0, 0), Point(6, 0)))
    world.add_agent(PathAwareAgent('parked', Point(3, 0), Point(3, 0)))
    world.run()
    event = next(e for e in collector.events if e['event_type'] == 'REACHED_STATE')
    assert event['tick'] == 0 and event['phase'] == 'pre_move'
    assert event['scope'] == 'reached_state_only'
    assert event['disconnected_agents'] == ['moving']
    assert not any(e['event_type'] == 'MOVE' for e in collector.events)


def test_component_index_matches_independent_transitive_closure_on_every_3x3_obstacle_map():
    from mapf.core.reachability import StaticConnectivity

    cells = [Point(x, y) for y in range(3) for x in range(3)]
    index = StaticConnectivity(3, 3)
    positions = {f'{i}:{j}': cells[i] for i, j in product(range(9), repeat=2)}
    goals = {f'{i}:{j}': cells[j] for i, j in product(range(9), repeat=2)}
    for mask in range(1 << 9):
        blocked = frozenset(p for i, p in enumerate(cells) if mask & (1 << i))
        matrix = [[p not in blocked and q not in blocked
                   and abs(p.x-q.x)+abs(p.y-q.y) <= 1 for q in cells] for p in cells]
        # Independent Floyd-Warshall reachability, not another component flood-fill.
        for via, i, j in product(range(9), repeat=3):
            matrix[i][j] |= matrix[i][via] and matrix[via][j]
        expected = {f'{i}:{j}' for i, j in product(range(9), repeat=2) if not matrix[i][j]}
        assert set(index.disconnected(positions, goals, blocked)) == expected
        # Repeated queries must retain the same answer; changed obstacles in the
        # next iteration must invalidate prior component labels.
        assert set(index.disconnected(positions, goals, blocked)) == expected
