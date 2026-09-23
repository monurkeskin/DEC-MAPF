"""Accepted proposals still require physical validation and atomic settlement."""

import pytest

from mapf.agents.base import BaseAgent
from mapf.agents.greedy import GreedyAgent
from mapf.core.models import BidDecision, Path
from mapf.negotiation.session import BilateralNegotiationSession
from tests.test_token_concession import Clock, parties


def test_invalid_accepted_response_is_rejected_before_a_later_legal_agreement(monkeypatch):
    args = parties(GreedyAgent, tokens=0)
    clock = Clock()

    def invalid_response(agent, bid, env, tick):
        clock.now += .001
        return BidDecision(accepted=True, proposed_path=Path(points=[agent.current_pos]), reason="TEST_INCOMPLETE")

    monkeypatch.setattr(BaseAgent, "propose_response", invalid_response)
    session = BilateralNegotiationSession(protocol="taop-v2", deadline_sec=1, clock=clock, sleeper=clock.sleep)
    contract = session.negotiate(*args, 0)
    assert contract is not None and session.last_session_reason == "AGREED"
    assert any(action["action"] == "CONTRACT_VALIDATION_FAILED" for action in session.last_diagnostics["recent_actions"])
    assert contract.path_a.points[-1] == args[0].target_pos
    assert contract.path_b.points[-1] == args[1].target_pos
    assert (args[0].tokens, args[1].tokens) == (0, 0)


def test_legacy_boolean_response_extension_still_reaches_legal_concession(monkeypatch):
    args = parties(GreedyAgent, tokens=1)
    monkeypatch.delattr(BaseAgent, "propose_response")
    session = BilateralNegotiationSession(protocol="taop-v2", deadline_sec=1)
    contract = session.negotiate(*args, 0)
    assert contract is not None
    assert any(action["action"] == "STRATEGY_REJECT" for action in session.last_diagnostics["recent_actions"])
    assert args[0].tokens + args[1].tokens == 2


def test_settlement_exception_cannot_leave_one_agent_paid(monkeypatch):
    args = parties(GreedyAgent, tokens=2)
    original = [agent.planned_path for agent in args[:2]]

    def broken(agent, contract, tick):
        agent.adjust_tokens(1)
        raise RuntimeError("injected settlement error")

    monkeypatch.setattr(BaseAgent, "on_contract_agreed", broken)
    session = BilateralNegotiationSession(protocol="taop-v2", deadline_sec=1)
    with pytest.raises(RuntimeError, match="settlement error"):
        session.negotiate(*args, 0)
    assert session.last_session_reason == "NEGOTIATION_ERROR"
    assert [agent.tokens for agent in args[:2]] == [2, 2]
    assert [agent.planned_path for agent in args[:2]] == original
