"""Independent counts for actual recipient information and local visibility."""

from dataclasses import FrozenInstanceError

import pytest

from mapf.agents.heatmap import HeatMapAgent
from mapf.core.models import Path, Point, SimulationConfig
from mapf.core.observations import Message
from mapf.engine.world import WorldSimulation
from mapf.metrics.communication import CommunicationLedger


def test_actual_delivery_counts_revisits_with_explicit_spatial_and_time_definitions():
    ledger = CommunicationLedger()
    message = Message("a", "b", 0, ((0, 0), (1, 0)))
    ledger.deliver(message)
    # A revisits its start at t=2, but only its first two states were delivered.
    metrics = ledger.metrics({"a": [Point(0, 0), Point(1, 0), Point(0, 0)],
                              "b": [Point(0, 1)]}, {"a": 5, "b": 5})
    assert metrics["information_sharing_rate"] == 0.5
    assert metrics["spacetime_information_sharing_rate"] == pytest.approx(1 / 3)
    assert metrics["message_count"] == 1
    assert metrics["payload_bytes"] == message.payload_bytes
    assert metrics["token_exchanges"] == 0
    assert metrics["token_gini"] == 0
    assert CommunicationLedger().metrics({"a": [Point(0, 0)]}, {"a": 0})["information_sharing_rate"] == 0


def test_local_view_has_no_global_agents_and_respects_broadcast_horizon():
    world = WorldSimulation(SimulationConfig(grid_width=12, grid_height=4, fov_size=3, broadcast_horizon=2))
    for aid, start, goal in [("a", Point(0, 0), Point(4, 0)), ("b", Point(0, 1), Point(4, 1)),
                             ("hidden", Point(10, 0), Point(10, 3))]:
        world.add_agent(HeatMapAgent(aid, start, goal, fov_size=3))
    world.initialize()
    local = world.for_agent("a")
    assert not hasattr(local, "agents")
    assert not hasattr(local, "world")
    broadcasts = local.get_fov_broadcasts(Point(0, 0), 3, "a")
    assert set(broadcasts) == {"b"}
    assert len(broadcasts["b"].points) == 2
    with pytest.raises(FrozenInstanceError):
        local.observation.tick = 20
    with pytest.raises(ValueError, match="another recipient"):
        local.get_fov_broadcasts(Point(0, 0), 3, "hidden")
    count = world._communication.messages
    world.for_agent("a")
    assert world._communication.messages == count  # reading does not transmit again


def test_heat_is_aligned_by_time_and_excludes_negotiating_opponent():
    world = WorldSimulation(SimulationConfig(grid_width=8, grid_height=8, fov_size=5))
    a = HeatMapAgent("a", Point(2, 2), Point(2, 4), fov_size=5)
    b = HeatMapAgent("b", Point(3, 2), Point(3, 4), fov_size=5)
    world.add_agent(a)
    world.add_agent(b)
    world.initialize()
    a._opponent_id = "b"
    assert a._compute_heatmap_weights(world.for_agent("a")) == {}
    a._opponent_id = None
    a._compute_heatmap_weights(world.for_agent("a"))
    first = Path(points=[Point(2, 2), Point(3, 3), Point(2, 4)])
    second = Path(points=[Point(2, 2), Point(2, 3), Point(2, 4)])
    assert a._estimate_path_heat(first) != a._estimate_path_heat(second)
