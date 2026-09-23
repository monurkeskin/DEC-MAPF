"""Compatibility protocols reject unfunded or conflicting agreements atomically."""

import pytest

from mapf.agents.greedy import GreedyAgent
from mapf.core.models import Bid, Path
from mapf.negotiation.session import BilateralNegotiationSession
from tests.test_negotiation_transactions import participants


class BooleanResponseAgent(GreedyAgent):
    """Represent the older plugin interface without the optional response bridge."""

    def __getattribute__(self, name):
        if name == "propose_response":
            raise AttributeError(name)
        return super().__getattribute__(name)


@pytest.mark.parametrize(
    "offered,reason", [(6, "INSUFFICIENT_TOKENS"), (0, "MAX_ROUNDS_TIMEOUT")]
)
def test_legacy_acceptance_is_not_enough_to_settle_an_invalid_bid(
    monkeypatch, offered, reason
):
    a, b, conflict, env = participants()
    original = a.planned_path, b.planned_path

    def bid(**kwargs):
        return Bid(bidder_id="a", proposed_path=a.planned_path, token_offered=offered)

    monkeypatch.setattr(a, "make_bid", bid)
    monkeypatch.setattr(b, "evaluate_bid", lambda **kwargs: True)
    session = BilateralNegotiationSession(max_rounds=1)
    assert session.negotiate(a, b, conflict, env, 0) is None
    assert session.last_session_reason == reason
    assert (a.tokens, b.tokens) == (5, 5)
    assert (a.planned_path, b.planned_path) == original


def test_taop_v1_accepts_boolean_plugin_responses_without_leaking_plan_mutation(
    monkeypatch,
):
    a, b, conflict, env = participants()
    original = a.planned_path, b.planned_path
    b.__class__ = BooleanResponseAgent

    def reject(*args):
        b.apply_planned_path(Path(points=[b.current_pos]))
        return False

    monkeypatch.setattr(b, "evaluate_bid", reject)
    session = BilateralNegotiationSession(
        max_rounds=1, protocol="taop-v1", deadline_sec=1
    )
    assert session.negotiate(a, b, conflict, env, 0) is None
    assert session.last_session_reason == "ROUND_BUDGET_EXHAUSTED"
    assert (a.planned_path, b.planned_path) == original
    assert (a.tokens, b.tokens) == (5, 5)
