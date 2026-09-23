"""Versioned article-prose TAOP; bounded path generators remain modern variants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mapf.agents.base import BaseAgent
from mapf.core.models import Bid, Conflict, Contract, Path
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol
from mapf.core.solution_validator import validate_solution
from mapf.negotiation._context import NegotiationContext
from mapf.negotiation.ledger import (
    OfferLedger,
    restore_agent,
    settle_contract,
    snapshot_agent,
)
from mapf.solvers.base import MAPFInstance
from mapf.telemetry.events import OfferBidEvent


@dataclass(frozen=True)
class _AcknowledgedOffer:
    full: Bid
    finite: Bid
    usage: int
    repeated: bool


def negotiate_taop(
    session: Any, a: AgentProtocol, b: AgentProtocol, conflict: Conflict,
    env: EnvironmentProtocol, tick: int,
) -> Contract | None:
    return _BoundedAlternation(NegotiationContext(session, a, b, conflict, env, tick)).run()


class _BoundedAlternation:
    """The historical offer cap and exhausted-token outcomes remain explicit."""

    def __init__(self, context: NegotiationContext) -> None:
        self.context = context
        self.session = context.session
        self.ledger = OfferLedger()
        self.session.last_offer_ledger = self.ledger
        self.session.last_settlement = None
        self.local = context.local_views()
        self.bidder, self.responder = context.participants
        self.last_bid: Bid | None = None

    def run(self) -> Contract | None:
        self._prepare()
        for turn in range(1, self.session.max_rounds + 1):
            self.session.check_deadline()
            self.session.last_session_rounds = turn
            offer = self._propose_and_acknowledge()
            if offer is None:
                return None
            accepted, response_path, decision = self._respond(offer.finite)
            self.session.check_deadline()
            self._record_response(offer, accepted, decision)
            if accepted:
                contract = self._settle(offer, response_path)
                if contract is not None:
                    return contract
            self.last_bid = offer.finite
            self.bidder, self.responder = self.responder, self.bidder
        self.session.last_session_reason = "ROUND_BUDGET_EXHAUSTED"
        return None

    def _prepare(self) -> None:
        ctx = self.context
        for agent, opponent in ((ctx.a, ctx.b), (ctx.b, ctx.a)):
            vars(agent)["_negotiation_reference_path"] = agent.planned_path
            vars(agent)["_acknowledged_usage"] = 0
            agent.on_pre_negotiation(opponent.agent_id, ctx.conflict, self.local[agent.agent_id], ctx.tick)
            ctx.record_heat(agent)
            self.session.check_deadline()

    def _propose_and_acknowledge(self) -> _AcknowledgedOffer | None:
        before = snapshot_agent(self.bidder)
        try:
            proposed = self.bidder.make_bid(self.responder.agent_id, self.last_bid,
                                           self.local[self.bidder.agent_id], self.context.tick, self.session.last_session_rounds)
        finally:
            restore_agent(self.bidder, before)
        self.session.check_deadline()
        allocation = self.context.allocation(proposed.proposed_path)
        if proposed.bidder_id != self.bidder.agent_id:
            self.session.last_session_reason = "WRONG_BIDDER"
            return None
        try:
            usage, repeated = self.ledger.acknowledge(self.bidder.agent_id, allocation, self.bidder.tokens)
        except ValueError:
            self.session.last_session_reason = "TOKEN_EXHAUSTED"
            return None
        bid = proposed.model_copy(update={"token_offered": usage, "proposed_path": allocation})
        vars(self.bidder)["_acknowledged_usage"] = usage
        vars(self.bidder)["_negotiation_reference_path"] = proposed.proposed_path
        if hasattr(self.context.env, "deliver_message"):
            self.context.env.deliver_message(self.bidder.agent_id, self.responder.agent_id, allocation, "OFFER",
                                             session_id=self.session.last_session_id, acknowledgement=usage)
        return _AcknowledgedOffer(proposed, bid, usage, repeated)

    def _respond(self, bid: Bid) -> tuple[bool, Path, dict[str, Any]]:
        # BaseAgent's pure bridge owns a complete transaction. Plugin overrides
        # and legacy callbacks need the outer snapshot as well.
        pure_bridge = getattr(getattr(self.responder, "propose_response", None), "__func__", None) is BaseAgent.propose_response
        snapshot = None if pure_bridge else snapshot_agent(self.responder)
        try:
            if hasattr(self.responder, "propose_response"):
                proposal = self.responder.propose_response(bid, self.local[self.responder.agent_id], self.context.tick)
                return proposal.accepted, proposal.proposed_path, proposal.components
            accepted = self.responder.evaluate_bid(bid, self.local[self.responder.agent_id], self.context.tick)
            return accepted, self.responder.planned_path.model_copy(deep=True), dict(getattr(self.responder, "_last_decision", {}))
        finally:
            if snapshot is not None:
                restore_agent(self.responder, snapshot)

    def _record_response(self, offer: _AcknowledgedOffer, accepted: bool, decision: dict[str, Any]) -> None:
        hook = getattr(self.context.env, "telemetry_hook", None)
        if hook is not None:
            hook.on_bid(OfferBidEvent(
                session_id=self.session.last_session_id, tick=self.context.tick,
                round_idx=self.session.last_session_rounds, agent_id=self.bidder.agent_id,
                path_length=offer.finite.proposed_path.length, path_heat=None, offered_utility=None,
                decision="ACCEPT" if accepted else "REJECT",
                reject_reason=decision.get("reason", "STRATEGY_ACCEPT" if accepted else "STRATEGY_REJECT"),
                utility_components={"responder": self.responder.agent_id, "response_evaluation": decision},
                token_usage=offer.usage, repeated_offer=offer.repeated))

    def _valid_paths(self, paths: dict[str, Path], allocation: Path) -> bool:
        ctx = self.context
        instance = MAPFInstance(starts={agent.agent_id: agent.current_pos for agent in ctx.participants},
                                goals={agent.agent_id: agent.target_pos for agent in ctx.participants},
                                grid_width=ctx.env.config.grid_width, grid_height=ctx.env.config.grid_height,
                                obstacles=ctx.env.config.obstacles)
        validation = validate_solution(instance, paths, ctx.env.config.setting)
        relevant_errors = [error for error in validation.errors if not (
            error.error_type in ("vertex_collision", "edge_collision") and error.time_step is not None
            and error.time_step >= len(allocation.points) - (error.error_type == "edge_collision"))]
        broken = any(isinstance(agent, BaseAgent) and not agent.respects_commitments(
            paths[agent.agent_id], ctx.tick, stay_at_goal=not ctx.env.config.setting.disappear_at_target
        ) for agent in ctx.participants)
        return not (relevant_errors or broken)

    def _settle(self, offer: _AcknowledgedOffer, response: Path) -> Contract | None:
        ctx = self.context
        transfer = self.ledger.payment(self.bidder.agent_id, self.responder.agent_id)
        paths = {self.bidder.agent_id: offer.full.proposed_path, self.responder.agent_id: response}
        allocation = offer.finite.proposed_path
        if not self._valid_paths(paths, allocation):
            self.session.last_session_reason = "CONTRACT_VALIDATION_FAILED"
            return None
        contract = Contract(session_id=self.session.last_session_id, agent_a=ctx.a.agent_id, agent_b=ctx.b.agent_id,
            path_a=paths[ctx.a.agent_id], path_b=paths[ctx.b.agent_id], timestamp=ctx.tick,
            token_transfer=transfer if self.bidder is ctx.a else -transfer,
            accepted_by=self.responder.agent_id, allocated_path=allocation, conflict_tick=ctx.conflict.end_time,
            token_usage=dict(self.ledger.usage), protocol_version="taop-v1")
        self.session.check_deadline()
        self.session.last_settlement = settle_contract(ctx.a, ctx.b, contract, ctx.tick)
        self.session.check_deadline()
        if hasattr(ctx.env, "record_settlement"):
            ctx.env.record_settlement(self.session.last_settlement)
        self.session.last_session_reason = "AGREED"
        return contract
