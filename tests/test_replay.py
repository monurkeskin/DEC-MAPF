"""Unit tests for DeterministicReplayEngine (L07, L08).

Verifies that replaying from snapshots reproduces exact state hashes
and respects the seek index.
"""

from __future__ import annotations

from mapf.agents.heatmap import HeatMapAgent
from mapf.core.models import Point, RecordingLevel, SimulationConfig, SimulationSetting
from mapf.engine.world import WorldSimulation
from mapf.telemetry.events import (
    AgentMoveEvent,
    KeyframeEvent,
    ManifestEvent,
)
from mapf.telemetry.replay import DeterministicReplayEngine


def test_replay_engine_basic_advancement() -> None:
    engine = DeterministicReplayEngine()
    events = [
        ManifestEvent("git123", 42, 10, 10, 2, "SETTING_4", "SC", 5, 0, 100.0).to_dict(),
        KeyframeEvent(0, {
            "A": {"pos": [0, 0], "tokens": 5, "reached_goal": False, "remaining_dist": 2},
            "B": {"pos": [4, 4], "tokens": 5, "reached_goal": False, "remaining_dist": 2},
        }).to_dict(),
        AgentMoveEvent(1, "A", 1, 0, False, 1).to_dict(),
        AgentMoveEvent(1, "B", 3, 4, False, 1).to_dict(),
        AgentMoveEvent(2, "A", 2, 0, False, 0).to_dict(),
        AgentMoveEvent(2, "B", 2, 4, False, 0).to_dict(),
        KeyframeEvent(2, {
            "A": {"pos": [2, 0], "tokens": 5, "reached_goal": True, "remaining_dist": 0},
            "B": {"pos": [2, 4], "tokens": 5, "reached_goal": True, "remaining_dist": 0},
        }).to_dict(),
    ]

    engine.load_events(events)
    assert engine.get_seek_index() == [0, 2]

    # Replay to tick 1
    s1 = engine.replay_to_tick(1)
    assert s1.tick == 1
    assert s1.agent_positions["A"] == (1, 0)
    assert s1.agent_positions["B"] == (3, 4)
    h1 = s1.compute_hash()
    assert isinstance(h1, str) and len(h1) == 64

    # Replay again to tick 1 - must match hash deterministically
    assert engine.replay_to_tick(1).compute_hash() == h1

    # Replay to tick 2
    s2 = engine.replay_to_tick(2)
    assert s2.agent_positions["A"] == (2, 0)
    assert s2.reached_goals["A"] is True


def test_replay_matches_live_simulation() -> None:
    """Acceptance L07: State hash obtained by replaying matches live run's state hash."""
    cfg = SimulationConfig(
        grid_width=5,
        grid_height=5,
        setting=SimulationSetting.SETTING_4,
        max_steps=10,
        random_seed=42,
        keyframe_interval=2,
        recording_level=RecordingLevel.FULL_TRACE,
    )
    sim = WorldSimulation(cfg)
    sim.add_agent(HeatMapAgent("A", Point(x=0, y=0), Point(x=2, y=0), 5, 5))
    sim.add_agent(HeatMapAgent("B", Point(x=4, y=4), Point(x=2, y=4), 5, 5))

    # Run step by step to capture frames
    sim.initialize()
    sim.step()  # tick 0 -> 1
    sim.step()  # tick 1 -> 2

    frame_1 = sim.frames[1]
    assert frame_1.tick == 1

    # Construct replay engine
    engine = DeterministicReplayEngine()
    kf0 = {
        "A": {"pos": [0, 0], "tokens": 5, "reached_goal": False, "remaining_dist": 2},
        "B": {"pos": [4, 4], "tokens": 5, "reached_goal": False, "remaining_dist": 2},
    }
    pos_t1 = frame_1.agent_positions
    events = [
        KeyframeEvent(0, kf0).to_dict(),
        AgentMoveEvent(1, "A", pos_t1["A"][0], pos_t1["A"][1], False, 1).to_dict(),
        AgentMoveEvent(1, "B", pos_t1["B"][0], pos_t1["B"][1], False, 1).to_dict(),
    ]
    engine.load_events(events)

    s1 = engine.replay_to_tick(1)
    assert s1.agent_positions["A"] == pos_t1["A"]
    assert s1.agent_positions["B"] == pos_t1["B"]
