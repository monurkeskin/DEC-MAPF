import pytest

from mapf.agents.heatmap import HeatMapAgent
from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import Path, Point, SimulationConfig
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar
from mapf.engine.world import WorldSimulation
from mapf.negotiation.conflict import detect_conflicts


@pytest.mark.parametrize("agent_type", [HeatMapAgent, PathAwareAgent])
def test_declared_horizon_applies_to_initial_agent_planning(agent_type):
    world = WorldSimulation(SimulationConfig(grid_width=5, grid_height=2, max_steps=1))
    agent = agent_type("a", Point(0, 0), Point(4, 0))
    world.add_agent(agent)
    world.initialize()
    assert agent.planned_path.points == (Point(0, 0),)


def test_future_goal_reservation_delays_first_arrival_without_goal_departure():
    reservations = ReservationTable()
    reservations.reserve_vertex("b", Point(1, 0), 2)
    planner = SpaceTimeAStar(3, 2)
    result = planner.search(Point(0, 0), Point(1, 0), reservation_table=reservations,
                            permanent_at_goal=True, max_time_steps=4)
    assert result is not None
    assert result.points.index(Point(1, 0)) == result.length == 3
    assert planner.last_search_status == "solved"
    assert planner.search(Point(0, 0), Point(2, 1), max_expansions=1) is None
    assert planner.last_search_status == "expansion_limit"


def test_conflict_action_horizon_includes_final_state_but_no_unobserved_edge():
    paths = {"a": Path([Point(0, 0), Point(1, 0), Point(2, 0)]),
             "b": Path([Point(2, 1), Point(2, 0), Point(1, 0)])}
    assert not detect_conflicts(paths, lookahead_steps=1)
    assert any(c.time == 1 for c in detect_conflicts(paths, lookahead_steps=2))
    paths["b"] = Path([Point(2, 1), Point(2, 1), Point(2, 0)])
    assert any(c.time == 2 for c in detect_conflicts(paths, lookahead_steps=2))
