"""Plugin failures must not commit proposals or look like successful sessions."""

from copy import deepcopy

import pytest

from mapf.agents.greedy import GreedyAgent
from mapf.core.models import Bid, Path, Point, SimulationConfig
from mapf.engine.world import WorldSimulation
from mapf.negotiation.conflict import detect_conflicts
from mapf.negotiation.session import BilateralNegotiationSession


def participants():
    env = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2))
    for aid, start, goal in [("a", Point(0, 0), Point(2, 0)), ("b", Point(2, 0), Point(0, 0))]:
        env.add_agent(GreedyAgent(aid, start, goal, 5))
    env.initialize()
    a, b = env.agents.values()
    conflict = detect_conflicts({"a": a.planned_path, "b": b.planned_path})[0]
    return a, b, conflict, env


@pytest.mark.parametrize("protocol", ["taop-v1", "taop-v2"])
@pytest.mark.parametrize("phase", ["proposal", "response"])
def test_callback_failure_restores_owned_state_and_records_an_error(monkeypatch, protocol, phase):
    a, b, conflict, env = participants()
    agent = a if phase == "proposal" else b
    agent.extension_state = {"choices": ["original"]}
    original = agent.planned_path
    lifecycle = []

    def broken(*args, **kwargs):
        agent.extension_state["choices"].append("uncommitted")
        agent.adjust_tokens(3)
        agent.apply_planned_path(Path(points=[agent.current_pos]))
        raise RuntimeError("injected plugin failure")

    method = "make_bid" if phase == "proposal" else "propose_response"
    monkeypatch.setattr(agent, method, broken)
    session = BilateralNegotiationSession(protocol=protocol, deadline_sec=1,
                                          lifecycle_hook=lambda event: lifecycle.append(deepcopy(event)))
    with pytest.raises(RuntimeError, match="injected plugin"):
        session.negotiate(a, b, conflict, env, 0)
    assert (a.tokens, b.tokens) == (5, 5)
    assert agent.planned_path == original
    assert agent.extension_state == {"choices": ["original"]}
    assert lifecycle[-1]["type"] == "negotiation_finished"
    assert lifecycle[-1]["reason"] == "NEGOTIATION_ERROR"
    assert lifecycle[-1]["diagnostics"]["error_type"] == "RuntimeError"


@pytest.mark.parametrize("protocol", ["taop-v1", "taop-v2"])
def test_wrong_bidder_identity_cannot_be_acknowledged(monkeypatch, protocol):
    args = participants()
    a, b = args[:2]
    monkeypatch.setattr(a, "make_bid", lambda *args: Bid(bidder_id="stranger", proposed_path=a.planned_path))
    session = BilateralNegotiationSession(protocol=protocol, deadline_sec=1)
    if protocol == "taop-v2":
        with pytest.raises(ValueError, match="identity"):
            session.negotiate(*args, 0)
    else:
        assert session.negotiate(*args, 0) is None
        assert session.last_session_reason == "WRONG_BIDDER"
    assert session.last_offer_ledger.usage == {}
    assert (a.tokens, b.tokens) == (5, 5)


def test_legacy_callbacks_keep_keyword_invocation_and_restore_rejected_plan(monkeypatch):
    a, b, conflict, env = participants()
    original = b.planned_path

    def bid(*, opponent_id, last_opponent_bid, env, current_time, round_num):
        return Bid(bidder_id=a.agent_id, proposed_path=a.planned_path)

    def reject(*, bid, env, current_time):
        b.apply_planned_path(Path(points=[b.current_pos]))
        return False

    monkeypatch.setattr(a, "make_bid", bid)
    monkeypatch.setattr(b, "evaluate_bid", reject)
    session = BilateralNegotiationSession(max_rounds=1)
    assert session.negotiate(a, b, conflict, env, 0) is None
    assert session.last_session_reason == "MAX_ROUNDS_TIMEOUT"
    assert b.planned_path == original
