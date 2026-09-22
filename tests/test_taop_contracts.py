"""Hand-counted protocol witnesses from article section 4; no score matching."""

import pytest

from mapf.agents.greedy import GreedyAgent
from mapf.core.models import CommitmentType, Contract, Path, Point
from mapf.core.space_time_grid import ReservationTable
from mapf.negotiation.ledger import OfferLedger, settle_contract


def path(y=0):
    return Path(points=[Point(0, y), Point(1, y), Point(2, y), Point(3, y)])


def test_repeating_any_prior_offer_costs_one_and_new_offer_keeps_usage():
    ledger = OfferLedger()
    assert ledger.acknowledge("a", path(), 2) == (0, False)
    assert ledger.acknowledge("a", path(1), 2) == (0, False)
    assert ledger.acknowledge("a", path(), 2) == (1, True)
    assert ledger.acknowledge("a", path(1), 2) == (2, True)
    assert ledger.acknowledge("b", path(), 2) == (0, False)
    assert ledger.payment("a", "b") == 2  # Fig. 2: acceptor receives two tokens
    assert ledger.payment("b", "a") == 0
    with pytest.raises(ValueError, match="exceeds"):
        ledger.acknowledge("a", path(), 2)
    assert ledger.usage["a"] == 2


@pytest.mark.parametrize("policy,after_conflict", [("SC", True), ("DC", False), ("ZC", True)])
def test_only_acceptor_obeys_allocated_path_and_dynamic_absolute_deadline(policy, after_conflict):
    a = GreedyAgent("a", Point(0, 0), Point(3, 0), 5, CommitmentType(policy))
    b = GreedyAgent("b", Point(0, 1), Point(3, 1), 5, CommitmentType(policy))
    contract = Contract(session_id="fixture", agent_a="a", agent_b="b", path_a=path(),
                        path_b=path(1), timestamp=10, token_transfer=2, accepted_by="b",
                        allocated_path=path(), conflict_tick=12, protocol_version="taop-v1")
    receipt = settle_contract(a, b, contract, 10)
    assert receipt["balances_after"] == {"a": 3, "b": 7}
    assert not a._commitments
    table = ReservationTable()
    b.reserve_commitments(table, 10)
    assert table.is_vertex_reserved(Point(2, 0), 12)
    assert table.is_vertex_reserved(Point(3, 0), 13) == after_conflict


def test_second_callback_failure_rolls_back_both_parties(monkeypatch):
    a = GreedyAgent("a", Point(0, 0), Point(3, 0), 5)
    b = GreedyAgent("b", Point(0, 1), Point(3, 1), 5)
    original = a.planned_path
    def broken(contract, tick):
        b.adjust_tokens(2)
        raise RuntimeError("injected second callback failure")
    monkeypatch.setattr(b, "on_contract_agreed", broken)
    contract = Contract(session_id="rollback", agent_a="a", agent_b="b", path_a=path(),
                        path_b=path(1), token_transfer=2)
    with pytest.raises(RuntimeError, match="second callback"):
        settle_contract(a, b, contract, 0)
    assert (a.tokens, b.tokens) == (5, 5)
    assert a.planned_path == original
    assert not a._commitments and not b._commitments


@pytest.mark.parametrize("policy", ["SC", "DC", "ZC"])
def test_published_fig2_allocations_payment_and_section41_role_obligations(policy):
    # Article p9: A receives (3,2) at t1 and (3,3) at t2, C receives two tokens.
    # p10: DC obeys this conflict through t2. The initial cells simply complete
    # these explicitly published allocations; no unreported score is asserted.
    offered = Path(points=[Point(3, 1), Point(3, 2), Point(3, 3)])
    response = Path(points=[Point(2, 2), Point(2, 3), Point(2, 4)])
    ledger = OfferLedger()
    assert ledger.acknowledge("A", offered, 5)[0] == 0
    assert ledger.acknowledge("C", response, 5)[0] == 0
    ledger.acknowledge("A", offered, 5)
    ledger.acknowledge("A", offered, 5)
    a = GreedyAgent("A", Point(3, 1), Point(3, 3), 5, CommitmentType(policy))
    c = GreedyAgent("C", Point(2, 2), Point(2, 4), 5, CommitmentType(policy))
    contract = Contract(session_id="published-fig2", agent_a="A", agent_b="C",
        path_a=offered, path_b=response, token_transfer=ledger.payment("A", "C"),
        accepted_by="C", allocated_path=offered, conflict_tick=2, protocol_version="taop-v1")
    settle_contract(a, c, contract, 0)
    assert (a.tokens, c.tokens) == (3, 7)
    assert not a._commitments
    table = ReservationTable(); c.reserve_commitments(table, 0)
    for point, tick in [(Point(3, 2), 1), (Point(3, 3), 2)]:
        assert table.is_vertex_reserved(point, tick)
    assert not table.is_vertex_reserved(Point(3, 3), 3)  # no invented perpetual commitment
