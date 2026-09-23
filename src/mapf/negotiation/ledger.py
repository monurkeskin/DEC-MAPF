"""TAOP offer accounting and atomic in-process settlement.

JAAMAS 38:10 (2024), section 4: a repeat of ANY earlier offer by the same
agent costs one acknowledgement token. Payment occurs only on agreement.
The prose/example and archived Java specify max(opponent usage - own usage, 0);
the printed min expression would imply a negative receipt and is not used.
"""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from mapf.core.models import Contract, Path, Point
from mapf.core.protocols import AgentProtocol


@dataclass
class OfferLedger:
    """Account for acknowledged allocations within a single bilateral session.

    Usage reserves an agent's available budget; it does not transfer balances.
    Only agreement settlement applies the positive payment between participants.
    """

    offers: dict[str, set[tuple[tuple[int, int], ...]]] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)

    def can_acknowledge(self, agent_id: str, path: Path, balance: int) -> bool:
        """Check affordability before committing an acknowledgement."""
        key = tuple((p.x, p.y) for p in path.points)
        if not key:
            raise ValueError("An offer must allocate at least the current position")
        return self.usage.get(agent_id, 0) + int(key in self.offers.get(agent_id, set())) <= balance

    def acknowledge(self, agent_id: str, path: Path, balance: int) -> tuple[int, bool]:
        key = tuple((p.x, p.y) for p in path.points)
        if not key:
            raise ValueError("An offer must allocate at least the current position")
        previous = self.offers.setdefault(agent_id, set())
        repeated = key in previous
        usage = self.usage.get(agent_id, 0) + int(repeated)
        if usage > balance:
            raise ValueError("Repeated offer exceeds available tokens")
        previous.add(key)
        self.usage[agent_id] = usage
        return usage, repeated

    def payment(self, proposer: str, acceptor: str) -> int:
        return max(0, self.usage.get(proposer, 0) - self.usage.get(acceptor, 0))


def snapshot_agent(agent: AgentProtocol) -> dict[str, Any]:
    """Capture owned strategy state, including extension fields, before a transaction.

    Strategies must keep external I/O out of proposal/settlement callbacks. Such
    external effects cannot be rolled back by an in-process state transaction.
    """
    # Profiling showed immutable Pydantic coordinates dominating snapshot copies.
    # Share only exact immutable value classes, without changing Pydantic's own
    # __deepcopy__ (model_copy(deep=True, update=...) must still create a new model).
    graph = _SnapshotGraph()
    graph.visit(vars(agent))
    return deepcopy(vars(agent), graph.immutable)


def _shareable_value(value: Any) -> bool:
    if type(value) is Point:
        return True
    return type(value) is Path and all(type(p) is Point for p in value.points)


def _children(value: Any) -> Iterator[Any]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield item
    elif isinstance(value, (list, tuple, set, frozenset)):
        yield from value


@dataclass
class _SnapshotGraph:
    immutable: dict[int, Any] = field(default_factory=dict)
    visited: set[int] = field(default_factory=set)

    def visit(self, value: Any) -> None:
        ident = id(value)
        if ident in self.visited:
            return
        self.visited.add(ident)
        if _shareable_value(value):
            self.immutable[ident] = value
            return
        for child in _children(value):
            self.visit(child)


def restore_agent(agent: AgentProtocol, snapshot: dict[str, Any]) -> None:
    vars(agent).clear()
    vars(agent).update(snapshot)


def settle_contract(
    a: AgentProtocol, b: AgentProtocol, contract: Contract, tick: int,
    *, verify_balances: bool = True,
) -> dict[str, Any]:
    """Commit both owned states or restore both after either callback fails."""
    before_a, before_b = snapshot_agent(a), snapshot_agent(b)
    balance_a, balance_b = a.tokens, b.tokens
    if verify_balances and min(balance_a - contract.token_transfer, balance_b + contract.token_transfer) < 0:
        raise ValueError("Contract would overdraw a token balance")
    try:
        a.on_contract_agreed(contract, tick)
        b.on_contract_agreed(contract, tick)
        if verify_balances:
            expected = (balance_a - contract.token_transfer, balance_b + contract.token_transfer)
            if (a.tokens, b.tokens) != expected:
                raise ValueError("Settlement callback violated token conservation")
    except BaseException:
        restore_agent(a, before_a)
        restore_agent(b, before_b)
        raise
    return {
        "event_type": "TOKEN_TRANSFER", "tick": tick,
        "session_id": contract.session_id, "agent_a": a.agent_id, "agent_b": b.agent_id,
        "payer": a.agent_id if contract.token_transfer >= 0 else b.agent_id,
        "payee": b.agent_id if contract.token_transfer >= 0 else a.agent_id,
        "amount": abs(contract.token_transfer),
        "signed_a_to_b": contract.token_transfer,
        "balances_before": {a.agent_id: balance_a, b.agent_id: balance_b},
        "balances_after": {a.agent_id: a.tokens, b.agent_id: b.tokens},
    }
