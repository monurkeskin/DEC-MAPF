"""Invalid offers and settlement callbacks leave owned state unchanged."""

from copy import deepcopy

import pytest

from mapf.core.models import Contract, Path
from mapf.negotiation.ledger import OfferLedger, settle_contract
from tests.test_negotiation_transactions import participants


@pytest.mark.parametrize("operation", ["can_acknowledge", "acknowledge"])
def test_empty_allocation_is_rejected_without_accounting(operation):
    ledger = OfferLedger()
    with pytest.raises(ValueError, match="current position"):
        getattr(ledger, operation)("a", Path(points=[]), 5)
    assert ledger.offers == {} and ledger.usage == {}


@pytest.mark.parametrize("failure", ["overdraw", "conservation"])
def test_settlement_cannot_spend_unavailable_tokens_or_keep_a_partial_callback(
    monkeypatch, failure
):
    a, b, _, _ = participants()
    before = deepcopy((vars(a), vars(b)))
    contract = Contract(
        session_id="session-test",
        agent_a="a",
        agent_b="b",
        path_a=a.planned_path,
        path_b=b.planned_path,
        token_transfer=6 if failure == "overdraw" else 1,
        timestamp=0,
    )
    if failure == "conservation":
        monkeypatch.setattr(
            type(b),
            "on_contract_agreed",
            lambda self, contract, tick: self.adjust_tokens(10),
        )
    with pytest.raises(ValueError, match="overdraw|conservation"):
        settle_contract(a, b, contract, 0)
    assert (vars(a), vars(b)) == before
