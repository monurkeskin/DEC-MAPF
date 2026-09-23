"""Malformed transfer receipts cannot invent participants or reconstruct invalid balances."""

import polars as pl
import pytest

from mapf.analytics.post_simulation import compute_token_inequality_gini


def transfer(before, after):
    return {"event_type": "TOKEN_TRANSFER", "balances_before": before, "balances_after": after}


@pytest.mark.parametrize(("before", "after", "roster"), [
    ({"a": 5, "b": 5}, {"a": 6, "c": 4}, ["a", "b"]),
    ({"a": 5, "c": 5}, {"a": 6, "c": 4}, ["a", "b"]),
    ({"a": -1, "b": 11}, {"a": 0, "b": 10}, None),
], ids=["changed-participants", "undeclared-participant", "negative-before"])
def test_inconsistent_transfer_participants_and_balances_are_rejected(before, after, roster):
    events = pl.DataFrame([transfer(before, after)])
    with pytest.raises(ValueError):
        compute_token_inequality_gini(events, agent_ids=roster)


def test_declared_roster_requires_nonnegative_initial_balance():
    with pytest.raises(ValueError, match="initial"):
        compute_token_inequality_gini(pl.DataFrame(), initial_tokens=-1, agent_ids=["a", "b"])


def test_valid_partial_receipts_preserve_uninvolved_roster_balances():
    events = pl.DataFrame([
        transfer({"a": 5, "b": 5}, {"a": 3, "b": 7}),
        transfer({"b": 7, "c": 5}, {"b": 6, "c": 6}),
    ])
    result = compute_token_inequality_gini(events, agent_ids=["a", "b", "c", "d"])
    assert result["balances"] == {"a": 3, "b": 6, "c": 6, "d": 5}
    assert result["roster_complete"]
    assert result["gini_coefficient"] == 0.125
