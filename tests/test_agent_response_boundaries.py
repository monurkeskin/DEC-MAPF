"""Handwritten decision and state invariants for the supported response policies."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from mapf.agents.greedy import GreedyAgent
from mapf.agents.heatmap import HeatMapAgent, HeatWeights
from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import (
    Bid,
    Contract,
    Path,
    Point,
    SimulationConfig,
    SimulationSetting,
)
from mapf.core.space_time_grid import SpaceTimeAStar


def environment(**values):
    return SimpleNamespace(config=SimulationConfig(grid_width=4, grid_height=4,
        setting=SimulationSetting.SETTING_2, **values),
        get_fov_obstacles=lambda *args: set(), get_fov_broadcasts=lambda **kwargs: {})


def route(delay=0):
    return Path(points=[Point(0, 0)] * (delay + 1) + [Point(1, 0), Point(2, 0)])


@pytest.mark.parametrize('strategy', [HeatMapAgent, PathAwareAgent])
@pytest.mark.parametrize(('protocol', 'delay', 'usage', 'offered', 'round_num', 'expected'), [
    ('taop-v1', 0, 0, 0, 0, True),
    ('taop-v1', 1, 5, 5, 9, False),
    ('taop-v2', 1, 0, 5, 0, False),
    ('taop-v2', 1, 5, 0, 0, True),
    ('taop-v2', 1, 4, 0, 0, True),
    ('legacy-alternating-v1', 0, 0, 0, 0, True),
    ('legacy-alternating-v1', 5, 0, 5, 0, True),
    ('legacy-alternating-v1', 1, 0, 0, 0, True),
    ('legacy-alternating-v1', 3, 0, 0, 2, True),
    ('legacy-alternating-v1', 3, 0, 0, 0, False),
    ('legacy-alternating-v1', 5, 0, 0, 9, False),
])
def test_response_rules_do_not_mix_token_bids_with_acknowledged_usage(
    monkeypatch, strategy, protocol, delay, usage, offered, round_num, expected,
):
    env = environment(negotiation_protocol=protocol)
    agent = strategy('a', Point(0, 0), Point(2, 0))
    agent.apply_planned_path(route())
    agent._initial_path_length = 6 if protocol == 'taop-v2' else 12
    agent._acknowledged_usage = usage
    alternative = route(delay)
    monkeypatch.setattr(SpaceTimeAStar, 'search', lambda *a, **kw: alternative)
    monkeypatch.setattr(SpaceTimeAStar, 'find_bounded_candidate_paths', lambda *a, **kw: [alternative])
    bid = Bid(bidder_id='b', proposed_path=Path(points=[Point(0, 2), Point(1, 2)]),
              token_offered=offered, round_num=round_num)
    before = agent.get_state()
    decision = agent.propose_response(bid, env, 0)
    assert decision.accepted is expected
    assert decision.components['delay'] == delay
    assert decision.proposed_path == (alternative if expected else before.remaining_path)
    assert agent.get_state() == before  # Response selection cannot settle tokens or mutate a plan.


@pytest.mark.parametrize('strategy', [HeatMapAgent, PathAwareAgent])
def test_legacy_concession_uses_remaining_resources(monkeypatch, strategy):
    env = environment(negotiation_protocol='legacy-alternating-v1')
    agent = strategy('a', Point(0, 0), Point(2, 0))
    agent.apply_planned_path(route())
    agent._initial_path_length = 12
    agent.adjust_tokens(-5)
    alternative = route(3)
    monkeypatch.setattr(SpaceTimeAStar, 'search', lambda *a, **kw: alternative)
    monkeypatch.setattr(SpaceTimeAStar, 'find_bounded_candidate_paths', lambda *a, **kw: [alternative])
    bid = Bid(bidder_id='b', proposed_path=Path(points=[Point(0, 2)]))
    assert agent.evaluate_bid(bid, env, 0)
    assert agent.planned_path == alternative and agent.tokens == 0


@pytest.mark.parametrize('strategy', [HeatMapAgent, PathAwareAgent])
def test_no_feasible_candidate_cannot_be_accepted(monkeypatch, strategy):
    agent = strategy('a', Point(0, 0), Point(2, 0))
    agent.apply_planned_path(route())
    monkeypatch.setattr(SpaceTimeAStar, 'search', lambda *a, **kw: None)
    monkeypatch.setattr(SpaceTimeAStar, 'find_bounded_candidate_paths', lambda *a, **kw: [])
    bid = Bid(bidder_id='b', proposed_path=Path(points=[Point(0, 2)]), token_offered=999)
    decision = agent.propose_response(bid, environment(), 0)
    assert not decision.accepted and decision.reason == 'NO_FEASIBLE_RESPONSE'
    assert agent.planned_path == route()


def test_heat_cache_reuses_immutable_values_but_invalidates_context():
    broadcasts = {'b': Path(points=[Point(1, 1), Point(1, 2)])}
    env = environment()
    env.get_fov_broadcasts = lambda **kw: broadcasts
    agent = HeatMapAgent('a', Point(0, 0), Point(2, 0))
    first = agent._compute_heatmap_weights(env)
    fields = agent._time_weights
    assert agent._compute_heatmap_weights(env) is first and agent._time_weights is fields
    agent._opponent_id = 'b'
    assert not agent._compute_heatmap_weights(env)
    assert first[Point(1, 1)] > 0  # A later bilateral exclusion cannot mutate prior evidence.


def test_heat_weights_cannot_be_replaced_or_subclass_snapshotted_implicitly():
    field = HeatWeights({Point(0, 0): 1.0})
    with pytest.raises(TypeError, match='immutable'):
        field._values = {}

    class MutableExtension(HeatWeights):
        pass

    with pytest.raises(TypeError, match='snapshot semantics'):
        deepcopy(MutableExtension({}))


@pytest.mark.parametrize(('party', 'transfer'), [('a', 6), ('b', -6)])
def test_contract_overdraft_rejects_before_plan_or_commitments_change(party, transfer):
    agent = GreedyAgent(party, Point(0, 0), Point(2, 0))
    before = agent.get_state()
    contract = Contract(session_id='invalid', agent_a='a', agent_b='b',
                        path_a=route(), path_b=route(1), token_transfer=transfer)
    with pytest.raises(ValueError, match='overdraft'):
        agent.on_contract_agreed(contract, 0)
    assert agent.get_state() == before


def test_nonparticipant_contract_has_no_effect():
    agent = GreedyAgent('c', Point(0, 0), Point(2, 0))
    before = agent.get_state()
    agent.on_contract_agreed(Contract(session_id='others', agent_a='a', agent_b='b',
        path_a=route(), path_b=route(1), token_transfer=100), 0)
    assert agent.get_state() == before


def test_unreachable_initial_and_forced_plans_remain_at_actual_position():
    env = environment(obstacles={Point(1, y) for y in range(4)})
    agent = GreedyAgent('a', Point(0, 0), Point(2, 0))
    assert agent.plan_initial_path(env).points == (Point(0, 0),)
    agent.force_move(Point(0, 1), env, 0)
    assert agent.current_pos == Point(0, 1) and agent.planned_path.points == (Point(0, 1),)
    assert not agent.reached_goal


def test_forced_arrival_stops_at_target():
    agent = GreedyAgent('a', Point(0, 0), Point(2, 0))
    agent.force_move(Point(2, 0), environment(), 0)
    assert agent.reached_goal and agent.planned_path.points == (Point(2, 0),)
    assert agent.step(1) == Point(2, 0)


def test_heat_concession_offer_avoids_the_opponents_swap_edge():
    agent = HeatMapAgent('a', Point(0, 0), Point(2, 0))
    agent.apply_planned_path(route())
    agent._initial_path_length = 2
    agent._acknowledged_usage = 5
    opposite = Bid(bidder_id='b', proposed_path=Path(points=[Point(1, 0), Point(0, 0)]))
    offer = agent.make_bid('b', opposite, environment(), 0, 5)
    assert offer.proposed_path.points[1] != Point(1, 0)
    assert offer.proposed_path.points[-1] == Point(2, 0)
    assert offer.token_offered == 0 and agent.tokens == 5


def test_heat_concession_without_a_candidate_keeps_its_existing_plan(monkeypatch):
    agent = HeatMapAgent('a', Point(0, 0), Point(2, 0))
    agent.apply_planned_path(route())
    agent._acknowledged_usage = 5
    monkeypatch.setattr(SpaceTimeAStar, 'find_bounded_candidate_paths', lambda *a, **kw: [])
    offer = agent.make_bid('b', None, environment(), 0, 5)
    assert offer.proposed_path == route() and offer.token_offered == 0
