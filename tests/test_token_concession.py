"""Source-grounded concession witnesses, not benchmark score assertions."""
import pytest

from mapf.agents.greedy import GreedyAgent
from mapf.agents.heatmap import HeatMapAgent
from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import (
    Bid,
    CommitmentType,
    Point,
    SimulationConfig,
    SimulationSetting,
)
from mapf.engine.world import WorldSimulation
from mapf.negotiation.conflict import detect_conflicts
from mapf.negotiation.session import BilateralNegotiationSession


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def parties(strategy=PathAwareAgent, *, tokens=5, height=2, commitment="SC", setting=SimulationSetting.SETTING_4):
    env = WorldSimulation(SimulationConfig(grid_width=3, grid_height=height, setting=setting,
                                          negotiation_protocol="taop-v2"))
    for aid, start, target in [("a", Point(0, 0), Point(2, 0)), ("b", Point(2, 0), Point(0, 0))]:
        env.add_agent(strategy(aid, start, target, tokens, commitment_type=CommitmentType(commitment)))
    env.initialize()
    a, b = env.agents.values()
    conflict = detect_conflicts({a.agent_id: a.planned_path, b.agent_id: b.planned_path})[0]
    return a, b, conflict, env


@pytest.mark.parametrize("strategy", [PathAwareAgent, HeatMapAgent])
def test_concession_accepts_feasible_longer_response_after_acknowledgements(strategy):
    a, b, _, env = parties(strategy)
    a._acknowledged_usage = 5
    a._negotiation_reference_path = a.planned_path
    bid = Bid(bidder_id="b", proposed_path=b.planned_path, token_offered=5, round_num=12)
    before = a.planned_path
    decision = a.propose_response(bid, env.for_agent("a"), 0)
    assert decision.accepted
    assert decision.proposed_path.length > before.length
    assert a.planned_path == before and a.tokens == 5
    assert decision.components["reason"] == "CONCEDE_FEASIBLE_RESPONSE"


@pytest.mark.parametrize("strategy", [PathAwareAgent, HeatMapAgent, GreedyAgent])
@pytest.mark.parametrize("commitment", ["SC", "DC", "ZC"])
@pytest.mark.parametrize("setting", list(SimulationSetting))
def test_zero_tokens_require_legal_concession_and_preserve_commitments(strategy, commitment, setting):
    a, b, conflict, env = parties(strategy, tokens=0, commitment=commitment, setting=setting)
    session = BilateralNegotiationSession(max_rounds=1, protocol="taop-v2", deadline_sec=1)
    contract = session.negotiate(a, b, conflict, env, 0)
    assert contract is not None
    assert a.tokens == b.tokens == 0
    assert contract.token_transfer == 0
    assert session.last_session_reason == "AGREED"
    acceptor = a if contract.accepted_by == "a" else b
    assert acceptor._commitments


@pytest.mark.parametrize("strategy", [PathAwareAgent, HeatMapAgent])
def test_five_each_reaches_agreement_beyond_offer_checkpoint_without_overdraft(strategy):
    args = parties(strategy)
    session = BilateralNegotiationSession(max_rounds=1, protocol="taop-v2", deadline_sec=1)
    contract = session.negotiate(*args, 0)
    assert contract is not None
    assert session.last_session_rounds > 1
    assert sum(agent.tokens for agent in args[:2]) == 10
    assert min(agent.tokens for agent in args[:2]) >= 0
    assert session.last_diagnostics["offer_checkpoint_reached"]


def test_no_legal_response_waits_for_same_deadline_and_keeps_diagnostic_evidence():
    args = parties(GreedyAgent, tokens=0, height=1, setting=SimulationSetting.SETTING_3)
    clock = Clock()
    session = BilateralNegotiationSession(max_rounds=1, protocol="taop-v2", deadline_sec=.1,
                                         clock=clock, sleeper=clock.sleep)
    assert session.negotiate(*args, 0) is None
    assert session.last_session_reason == "NEGOTIATION_DEADLINE"
    assert clock.now >= .1
    assert session.last_diagnostics["unaffordable_repeats"] > 0
    assert session.last_diagnostics["concession_failures"] > 0
    assert session.last_diagnostics["recent_actions"]
    assert args[0].tokens == args[1].tokens == 0


def test_pre_v13_protocol_remains_explicitly_bounded():
    args = parties(GreedyAgent, tokens=0)
    session = BilateralNegotiationSession(max_rounds=10, protocol="taop-v1", deadline_sec=1)
    assert session.negotiate(*args, 0) is None
    assert session.last_session_reason == "TOKEN_EXHAUSTED"


def test_strategy_local_view_cannot_emit_supervisor_lifecycle_messages():
    a, _, _, env = parties()
    env.config.negotiation_lifecycle_hook = lambda _: None
    assert env.for_agent(a.agent_id).config.negotiation_lifecycle_hook is None


def test_progress_cannot_renew_deadline_or_attach_to_another_session():
    from mapf.application.deadlines import NegotiationWatch
    watch = NegotiationWatch()
    watch.receive({"type": "negotiation_started", "session_id": "a", "deadline": 60})
    watch.receive({"type": "negotiation_progress", "session_id": "a", "deadline": 600,
                   "diagnostics": {"phase": "proposal", "round": 8}})
    assert watch.deadline == 60 and watch.expired(60)
    with pytest.raises(ValueError, match="Stale"):
        watch.receive({"type": "negotiation_progress", "session_id": "b", "diagnostics": {}})
