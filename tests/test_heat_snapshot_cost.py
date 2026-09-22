"""Heat values can be shared only when immutable; plugin transaction state cannot."""

from copy import deepcopy

import pytest

from mapf.agents.heatmap import HeatMapAgent
from mapf.core.models import Path, Point, SimulationConfig
from mapf.engine.world import WorldSimulation
from mapf.negotiation.ledger import restore_agent, snapshot_agent


def test_heat_fields_are_readonly_and_safe_to_share_across_transaction_snapshots():
    world = WorldSimulation(SimulationConfig(grid_width=8, grid_height=8, fov_size=5))
    a = HeatMapAgent("a", Point(2, 2), Point(2, 6), fov_size=5)
    b = HeatMapAgent("b", Point(3, 2), Point(3, 6), fov_size=5)
    world.add_agent(a)
    world.add_agent(b)
    world.initialize()
    local = world.for_agent("a")
    a._cell_weights = a._compute_heatmap_weights(local)
    assert a._cell_weights[Point(3, 2)] > 0
    before = dict(a._cell_weights)
    with pytest.raises(TypeError):
        a._cell_weights[Point(3, 2)] = 999
    with pytest.raises(TypeError):
        a._time_weights[0][Point(3, 2)] = 999
    assert deepcopy(a._cell_weights) is a._cell_weights
    a.plugin_state = {"nested": [1]}
    snapshot = snapshot_agent(a)
    assert snapshot["_cell_weights"] is a._cell_weights
    a.plugin_state["nested"].append(2)
    a._opponent_id = "b"
    a._cell_weights = a._compute_heatmap_weights(local)
    assert not a._cell_weights
    restore_agent(a, snapshot)
    assert dict(a._cell_weights) == before and a.plugin_state == {"nested": [1]}
    # An updated broadcast produces a new field; old snapshots cannot change.
    b.apply_planned_path(Path(points=[Point(3, 2), Point(4, 2)]))
    updated = a._compute_heatmap_weights(world.for_agent("a"))
    assert dict(updated) != before and dict(snapshot["_cell_weights"]) == before


def test_heat_field_constructor_detaches_input_and_cannot_delete_values():
    from mapf.agents.heatmap import HeatWeights

    original = {Point(1, 2): 3.0}
    field = HeatWeights(original)
    original[Point(1, 2)] = 99.0
    assert field[Point(1, 2)] == 3.0
    with pytest.raises(TypeError):
        del field._values


def test_delivered_message_wire_bytes_are_exact_and_do_not_need_recursive_copy():
    from mapf.core.observations import Message

    m = Message("a", "b", 5, ((0, 1), (1, 1)))
    expected = b'{"acknowledgement":0,"kind":"BROADCAST","points":[[0,1],[1,1]],"recipient":"b","sender":"a","session_id":null,"tick":5}'
    assert m.payload_bytes == len(expected)
    import json

    payload = {
        k: v for k, v in m.to_dict().items() if k not in {"event_type", "payload_bytes"}
    }
    assert (
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() == expected
    )


def test_fast_goal_flag_preserves_custom_state_and_property_overrides():
    from mapf.agents.base import goal_reached
    from mapf.agents.greedy import GreedyAgent

    base = GreedyAgent("a", Point(0, 0), Point(2, 0))
    assert not goal_reached(base)

    class CustomState(GreedyAgent):
        def get_state(self):
            return super().get_state().model_copy(update={"reached_goal": True})

    assert goal_reached(CustomState("b", Point(0, 0), Point(2, 0)))

    class CustomProperty(GreedyAgent):
        @property
        def reached_goal(self):
            return True

    # Existing engine semantics came from get_state(), not a contradictory plugin property.
    assert not goal_reached(CustomProperty("c", Point(0, 0), Point(2, 0)))


@pytest.mark.parametrize("custom_bridge", [False, True])
@pytest.mark.parametrize("raises", [False, True])
def test_taop_bridge_restores_owned_plugin_state_on_rejection_or_exception(
    monkeypatch, custom_bridge, raises
):
    from mapf.agents.greedy import GreedyAgent
    from mapf.core.models import BidDecision
    from mapf.negotiation.conflict import detect_conflicts
    from mapf.negotiation.session import BilateralNegotiationSession

    env = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2))
    a = GreedyAgent("a", Point(0, 0), Point(2, 0))
    b = GreedyAgent("b", Point(2, 0), Point(0, 0))
    env.add_agent(a)
    env.add_agent(b)
    env.initialize()
    b.plugin_state = {"nested": [1]}
    original_path = b.planned_path

    def mutate(*args, **kwargs):
        b.plugin_state["nested"].append(99)
        b.adjust_tokens(-2)
        b.apply_planned_path(Path(points=[Point(2, 0), Point(2, 1)]))
        if raises:
            raise RuntimeError("injected response failure")
        return (
            BidDecision(accepted=False, proposed_path=b.planned_path, reason="fixture")
            if custom_bridge
            else False
        )

    monkeypatch.setattr(
        b, "propose_response" if custom_bridge else "evaluate_bid", mutate
    )
    session = BilateralNegotiationSession(max_rounds=1, protocol="taop-v1")
    conflict = detect_conflicts({"a": a.planned_path, "b": b.planned_path})[0]
    if raises:
        with pytest.raises(RuntimeError, match="injected response failure"):
            session.negotiate(a, b, conflict, env, 0)
    else:
        assert session.negotiate(a, b, conflict, env, 0) is None
    assert b.plugin_state == {"nested": [1]}
    assert b.tokens == 5 and b.planned_path == original_path
