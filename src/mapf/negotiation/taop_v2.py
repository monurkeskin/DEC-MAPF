"""Token-limited insistence with legal concessions and one absolute deadline.

Article section 4 requires a new offer or a paid repeat. Java's run_concede
accepts a feasible opponent allocation. Search remains bounded, so inability to
construct a concession is logged and retried within the same session deadline.
"""
from typing import Any

from mapf.core.models import Bid, BidDecision, Conflict, Contract, Path
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol
from mapf.negotiation._context import NegotiationContext
from mapf.negotiation.agreement import admit_agreement
from mapf.negotiation.concession import feasible_concession, novel_offer
from mapf.negotiation.ledger import OfferLedger, restore_agent, snapshot_agent
from mapf.telemetry.events import OfferBidEvent


def negotiate_taop_v2(session: Any, a: AgentProtocol, b: AgentProtocol, conflict: Conflict,
                      env: EnvironmentProtocol, tick: int) -> Contract | None:
    return _TokenAlternation(NegotiationContext(session, a, b, conflict, env, tick)).run()


class _TokenAlternation:
    """Own offers and acknowledgements until a legal agreement or the deadline."""

    def __init__(self, context: NegotiationContext) -> None:
        self.context = context
        self.session = context.session
        self.ledger = OfferLedger()
        self.session.last_offer_ledger = self.ledger
        self.session.last_settlement = None
        self.local = context.local_views()
        self.offers: dict[str, Bid] = {}
        self.bidder, self.responder = context.participants
        self.horizon = 0

    def run(self) -> Contract | None:
        self._prepare()
        turn = 0
        while True:
            self.session.check_deadline()
            turn += 1
            self.session.last_session_rounds = turn
            self.session.last_diagnostics["offer_checkpoint_reached"] = turn >= self.session.max_rounds
            contract = self._turn()
            if contract is not None:
                return contract
            self.bidder, self.responder = self.responder, self.bidder

    def _prepare(self) -> None:
        ctx = self.context
        for agent, other in ((ctx.a, ctx.b), (ctx.b, ctx.a)):
            vars(agent)["_negotiation_reference_path"] = agent.planned_path
            vars(agent)["_acknowledged_usage"] = 0
            self.session.progress("prepare", agent=agent.agent_id)
            agent.on_pre_negotiation(other.agent_id, ctx.conflict, self.local[agent.agent_id], ctx.tick)
            ctx.record_heat(agent)
            self.session.check_deadline()
        self.horizon = ctx.env.config.negotiation_horizon or ctx.env.config.fov_size

    def _finite(self, offer: Bid | None) -> Bid | None:
        return None if offer is None else offer.model_copy(update={
            "proposed_path": Path(points=offer.proposed_path.points[:self.horizon])})

    def _propose(self) -> Bid:
        self.session.progress("proposal", agent=self.bidder.agent_id, acknowledged_usage=dict(self.ledger.usage))
        before = snapshot_agent(self.bidder)
        try:
            proposed = self.bidder.make_bid(self.responder.agent_id, self._finite(self.offers.get(self.responder.agent_id)),
                                            self.local[self.bidder.agent_id], self.context.tick, self.session.last_session_rounds)
        finally:
            restore_agent(self.bidder, before)
        self.session.check_deadline()
        if proposed.bidder_id != self.bidder.agent_id:
            raise ValueError("TAOP bidder identity does not match the active participant")
        return proposed

    def _turn(self) -> Contract | None:
        proposed = self._propose()
        allocation = self.context.allocation(proposed.proposed_path)
        if not self.ledger.can_acknowledge(self.bidder.agent_id, allocation, self.bidder.tokens):
            contract = self._concede_previous()
            if contract is not None:
                return contract
            alternative = self._find_novel()
            if alternative is None:
                return None
            proposed = proposed.model_copy(update={"proposed_path": alternative})
            allocation = self.context.allocation(alternative)
        return self._evaluate_offer(proposed, allocation)

    def _evaluate_offer(self, proposed: Bid, allocation: Path) -> Contract | None:
        """Acknowledge one affordable offer, then validate any accepted response."""
        bid, usage, repeated = self._acknowledge(proposed, allocation)
        response = self._respond(bid)
        self.session.action(response.reason, agent=self.responder.agent_id, **response.components)
        self._record_response(bid, response, usage, repeated)
        if response.accepted:
            contract = self._settle(self.bidder, self.responder, proposed, response.proposed_path)
            if contract is not None:
                return contract
            self.session.action("CONTRACT_VALIDATION_FAILED", agent=self.responder.agent_id)
        return None

    def _concede_previous(self) -> Contract | None:
        self.session.last_diagnostics["unaffordable_repeats"] += 1
        opponent_offer = self.offers.get(self.responder.agent_id)
        if opponent_offer is None:
            return None
        self.session.progress("forced_concession", agent=self.bidder.agent_id)
        finite_opponent = self._finite(opponent_offer)
        assert finite_opponent is not None
        response = feasible_concession(self.bidder, finite_opponent, self.local[self.bidder.agent_id], self.context.tick)
        self.session.check_deadline()
        self.session.action(response.reason, agent=self.bidder.agent_id, **response.components)
        if response.accepted:
            contract = self._settle(self.responder, self.bidder, opponent_offer, response.proposed_path)
            if contract is not None:
                return contract
        self.session.last_diagnostics["concession_failures"] += 1
        return None

    def _find_novel(self) -> Path | None:
        self.session.progress("novel_offer_search", agent=self.bidder.agent_id)
        alternative = novel_offer(self.bidder, self.ledger, self.local[self.bidder.agent_id], self.context.tick)
        self.session.check_deadline()
        if alternative is None:
            self.session.action("NO_NOVEL_OFFER_FOUND", agent=self.bidder.agent_id)
            self.session.pause_for_retry()
        return alternative

    def _acknowledge(self, proposed: Bid, allocation: Path) -> tuple[Bid, int, bool]:
        usage, repeated = self.ledger.acknowledge(self.bidder.agent_id, allocation, self.bidder.tokens)
        vars(self.bidder)["_acknowledged_usage"] = usage
        vars(self.bidder)["_negotiation_reference_path"] = proposed.proposed_path
        self.offers[self.bidder.agent_id] = proposed
        bid = proposed.model_copy(update={"token_offered": usage, "proposed_path": allocation})
        if hasattr(self.context.env, "deliver_message"):
            self.context.env.deliver_message(self.bidder.agent_id, self.responder.agent_id, allocation, "OFFER",
                                             session_id=self.session.last_session_id, acknowledgement=usage)
        return bid, usage, repeated

    def _respond(self, bid: Bid) -> BidDecision:
        self.session.progress("response", agent=self.responder.agent_id, acknowledged_usage=dict(self.ledger.usage))
        before = snapshot_agent(self.responder)
        response: BidDecision
        try:
            if hasattr(self.responder, "propose_response"):
                response = self.responder.propose_response(bid, self.local[self.responder.agent_id], self.context.tick)
            else:
                accepted = self.responder.evaluate_bid(bid, self.local[self.responder.agent_id], self.context.tick)
                response = BidDecision(accepted=accepted, proposed_path=self.responder.planned_path,
                                       reason="STRATEGY_ACCEPT" if accepted else "STRATEGY_REJECT")
        finally:
            restore_agent(self.responder, before)
        self.session.check_deadline()
        if not response.accepted and self.ledger.usage.get(self.responder.agent_id, 0) >= self.responder.tokens:
            self.session.progress("forced_concession", agent=self.responder.agent_id)
            response = feasible_concession(self.responder, bid, self.local[self.responder.agent_id], self.context.tick)
            self.session.check_deadline()
            if not response.accepted:
                self.session.last_diagnostics["concession_failures"] += 1
        return response

    def _record_response(self, bid: Bid, response: BidDecision, usage: int, repeated: bool) -> None:
        hook = getattr(self.context.env, "telemetry_hook", None)
        if hook is not None:
            hook.on_bid(OfferBidEvent(session_id=self.session.last_session_id, tick=self.context.tick,
                round_idx=self.session.last_session_rounds, agent_id=self.bidder.agent_id,
                path_length=bid.proposed_path.length, path_heat=None, offered_utility=None,
                decision="ACCEPT" if response.accepted else "REJECT", reject_reason=response.reason,
                utility_components={"responder": self.responder.agent_id, "response_evaluation": response.components},
                token_usage=usage, repeated_offer=repeated))

    def _settle(self, proposer: AgentProtocol, acceptor: AgentProtocol, offered: Bid, response: Path) -> Contract | None:
        ctx = self.context
        self.session.progress("settlement", agent=acceptor.agent_id)
        return admit_agreement(self.session, ctx.a, ctx.b, proposer, acceptor, offered, response,
                               ctx.conflict, ctx.env, ctx.tick, self.ledger)
