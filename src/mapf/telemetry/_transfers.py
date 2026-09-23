"""Validate a recorded transfer before changing reconstructed token state."""

from typing import Any


def _balances(value: dict[str, Any]) -> dict[str, int]:
    if any(type(balance) is not int or balance < 0 for balance in value.values()):
        raise ValueError("Token receipt contains invalid or overdrawn balances")
    return dict(value)


def apply_transfer(current: dict[str, int], event: dict[str, Any]) -> dict[str, int]:
    """Apply only conserved, correctly attributed receipts consistent with known state."""
    before, after = _balances(event["balances_before"]), _balances(event["balances_after"])
    if before.keys() != after.keys():
        raise ValueError("Token receipt changes its participant roster")
    amount = event["amount"]
    if type(amount) is not int or amount < 0:
        raise ValueError("Token transfer amount must be a nonnegative integer")
    payer, payee = event["payer"], event["payee"]
    if payer not in before or payee not in before:
        raise ValueError("Token receipt omits its payer or payee")
    expected = dict(before)
    expected[payer] -= amount
    expected[payee] += amount
    if after != expected:
        raise ValueError("Token receipt violates the declared transfer or conservation")
    for aid, balance in before.items():
        if aid in current and current[aid] != balance:
            raise ValueError("Token receipt does not match prior replay balance")
    return {**current, **after}
