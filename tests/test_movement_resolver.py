from __future__ import annotations

import pytest

from mapf.agents.heatmap import HeatMapAgent
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.engine.movement import MovementResolver
from mapf.engine.world import WorldSimulation


@pytest.fixture
def dummy_env():
    cfg = SimulationConfig(
        grid_width=10,
        grid_height=10,
        setting=SimulationSetting.SETTING_1,
    )
    return WorldSimulation(cfg)


def test_movement_resolver_clean_step(dummy_env):
    """Disjoint moves proceed without any conflict."""
    a1 = HeatMapAgent("A_01", Point(x=1, y=1), Point(x=5, y=1), initial_tokens=5)
    a2 = HeatMapAgent("A_02", Point(x=2, y=5), Point(x=8, y=5), initial_tokens=5)
    active = {"A_01": a1, "A_02": a2}
    desired = {"A_01": Point(x=2, y=1), "A_02": Point(x=3, y=5)}

    resolved = MovementResolver.resolve_step(
        active_agents=active,
        desired_moves=desired,
        occupied_permanent={},
        allow_wait=False,
        env=dummy_env,
    )
    assert resolved["A_01"] == Point(x=2, y=1)
    assert resolved["A_02"] == Point(x=3, y=5)


def test_movement_resolver_vertex_conflict_wait_allowed(dummy_env):
    """When allow_wait=True, conflicting lower-priority agent holds position."""
    a1 = HeatMapAgent("A_01", Point(x=1, y=1), Point(x=3, y=1), initial_tokens=10)
    a2 = HeatMapAgent("A_02", Point(x=3, y=1), Point(x=1, y=1), initial_tokens=2)
    active = {"A_01": a1, "A_02": a2}
    desired = {"A_01": Point(x=2, y=1), "A_02": Point(x=2, y=1)}

    resolved = MovementResolver.resolve_step(
        active_agents=active,
        desired_moves=desired,
        occupied_permanent={},
        allow_wait=True,
        env=dummy_env,
    )
    assert resolved["A_01"] == Point(x=2, y=1)
    assert resolved["A_02"] == Point(x=3, y=1)  # A_02 waits at cur


def test_movement_resolver_vertex_conflict_evasion_no_wait(dummy_env):
    """When allow_wait=False, conflicting lower-priority agent takes lateral evasion."""
    a1 = HeatMapAgent("A_01", Point(x=1, y=1), Point(x=3, y=1), initial_tokens=10)
    a2 = HeatMapAgent("A_02", Point(x=3, y=1), Point(x=1, y=1), initial_tokens=2)
    active = {"A_01": a1, "A_02": a2}
    desired = {"A_01": Point(x=2, y=1), "A_02": Point(x=2, y=1)}

    resolved = MovementResolver.resolve_step(
        active_agents=active,
        desired_moves=desired,
        occupied_permanent={},
        allow_wait=False,
        env=dummy_env,
    )
    assert resolved["A_01"] == Point(x=2, y=1)
    # A_02 cannot move to (2,1); takes lateral evasion, e.g. (3,0) or (3,2) or (4,1)
    assert resolved["A_02"] != Point(x=2, y=1)
    assert resolved["A_02"] in [Point(x=3, y=0), Point(x=3, y=2), Point(x=4, y=1)]


def test_movement_resolver_edge_swap_conflict(dummy_env):
    """Head-on edge swap resolved without collision."""
    a1 = HeatMapAgent("A_01", Point(x=2, y=1), Point(x=5, y=1), initial_tokens=10)
    a2 = HeatMapAgent("A_02", Point(x=3, y=1), Point(x=0, y=1), initial_tokens=2)
    active = {"A_01": a1, "A_02": a2}
    desired = {"A_01": Point(x=3, y=1), "A_02": Point(x=2, y=1)}

    resolved = MovementResolver.resolve_step(
        active_agents=active,
        desired_moves=desired,
        occupied_permanent={},
        allow_wait=False,
        env=dummy_env,
    )
    assert resolved["A_01"] == Point(x=3, y=1)
    assert resolved["A_02"] != Point(x=2, y=1)
    assert resolved["A_02"] in [Point(x=3, y=0), Point(x=3, y=2), Point(x=4, y=1)]
