from __future__ import annotations

from mapf.agents.heatmap import HeatMapAgent
from mapf.agents.path_aware import PathAwareAgent
from mapf.core.components import (
    NegotiationComponent,
    PathPlanningComponent,
    SimFrame,
    SpatialComponent,
)
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.engine.world import WorldSimulation


def test_pipeline_components_creation():
    """Verify decoupled components instantiate correctly."""
    spatial = SpatialComponent(current_pos=Point(x=1, y=2), target_pos=Point(x=5, y=2))
    assert spatial.distance_to_goal == 4
    assert not spatial.reached_goal

    nego = NegotiationComponent(tokens=10, strategy="HeatMap")
    nego.adjust_tokens(-3)
    assert nego.tokens == 7

    planning = PathPlanningComponent()
    planning.commitments = {1: Point(x=1, y=2), 5: Point(x=2, y=2)}
    planning.prune_commitments(current_time=2)
    assert 1 not in planning.commitments
    assert 5 in planning.commitments


def test_simulation_pipeline_execution():
    """Verify 5-stage pipeline advances simulation state cleanly."""
    cfg = SimulationConfig(
        grid_width=8,
        grid_height=8,
        setting=SimulationSetting.SETTING_4,
        max_steps=50,
        random_seed=42,
    )
    sim = WorldSimulation(cfg)
    a1 = HeatMapAgent("A_01", Point(x=0, y=0), Point(x=4, y=0), initial_tokens=5)
    a2 = PathAwareAgent("A_02", Point(x=4, y=0), Point(x=0, y=0), initial_tokens=5)
    sim.add_agent(a1)
    sim.add_agent(a2)
    sim.initialize()

    # Execute 1 step via pipeline
    all_done = sim.step()
    assert not all_done
    assert sim.current_time == 1
    assert len(sim.frames) == 1
    frame = sim.frames[0]
    assert isinstance(frame, SimFrame)
    assert frame.tick == 0
    assert "A_01" in frame.agent_positions
    assert "A_02" in frame.agent_positions


def test_pipeline_unsolvable_setting1_detection():
    """Verify Setting 1 permanent blockage triggers instant unsolvable exit."""
    cfg = SimulationConfig(
        grid_width=5,
        grid_height=5,
        obstacles={Point(x=1, y=3), Point(x=3, y=3), Point(x=2, y=4)},
        setting=SimulationSetting.SETTING_1,
        max_steps=20,
        random_seed=42,
    )
    sim = WorldSimulation(cfg)
    # A_01 is already at its target and parked
    a1 = HeatMapAgent("A_01", Point(x=2, y=2), Point(x=2, y=2), initial_tokens=5)
    # A_02 needs to cross (2,2) and is boxed in
    a2 = HeatMapAgent("A_02", Point(x=2, y=1), Point(x=2, y=3), initial_tokens=5)
    sim.add_agent(a1)
    sim.add_agent(a2)
    sim.initialize()

    res = sim.run()
    assert not res["success"]
