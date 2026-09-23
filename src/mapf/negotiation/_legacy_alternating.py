"""Historical alternating bids with explicit impasse and token stopping rules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from mapf.core.models import Bid, Contract, Path
from mapf.core.protocols import AgentProtocol
from mapf.negotiation._context import NegotiationContext
from mapf.negotiation.contract import validate_contract
from mapf.negotiation.ledger import settle_contract
from mapf.telemetry.events import OfferBidEvent

logger = logging.getLogger("mapf.negotiation")


@dataclass
class _BidHistory:
    previous: dict[str, Bid] = field(default_factory=dict)
    stagnations: int = 0

    def stalled(self, bidder: AgentProtocol, bid: Bid) -> bool:
        previous = self.previous.get(bidder.agent_id)
        unchanged = previous is not None and bid.proposed_path == previous.proposed_path
        no_increase = previous is not None and bid.token_offered <= previous.token_offered
        self.stagnations = self.stagnations + 1 if unchanged and no_increase else 0
        return self.stagnations >= 2


class LegacyAlternating:
    def __init__(self, context: NegotiationContext) -> None:
        self.context = context
        self.session = context.session
        self.history = _BidHistory()
        self.bidder, self.responder = context.participants
        self.last_bid: Bid | None = None

    def run(self) -> Contract | None:
        self._prepare()
        for turn in range(1, self.session.max_rounds + 1):
            self.session.check_deadline()
            self.session.last_session_rounds = turn
            bid = self.bidder.make_bid(opponent_id=self.responder.agent_id, last_opponent_bid=self.last_bid,
                                       env=self.context.env, current_time=self.context.tick, round_num=turn)
            self.session.check_deadline()
            if self.history.stalled(self.bidder, bid):
                self._record_impasse(bid)
                return None
            self.session.check_deadline()
            self.history.previous[self.bidder.agent_id] = bid
            accepted, response = self._evaluate(bid)
            self.session.check_deadline()
            self._record_bid(bid, accepted)
            if accepted:
                contract = self._settle(bid, response)
                if contract is not None or self.session.last_session_reason == "INSUFFICIENT_TOKENS":
                    return contract
            self.last_bid = bid
            self.bidder, self.responder = self.responder, self.bidder
        self.session.last_session_reason = "MAX_ROUNDS_TIMEOUT"
        return None

    def _prepare(self) -> None:
        ctx = self.context
        for agent, other in ((ctx.a, ctx.b), (ctx.b, ctx.a)):
            agent.on_pre_negotiation(other.agent_id, ctx.conflict, ctx.env, ctx.tick)
            ctx.record_heat(agent)
            self.session.check_deadline()

    def _evaluate(self, bid: Bid) -> tuple[bool, Path]:
        before = self.responder.planned_path
        try:
            accepted = self.responder.evaluate_bid(bid=bid, env=self.context.env, current_time=self.context.tick)
            proposal = self.responder.planned_path
        finally:
            if self.responder.planned_path != before:
                self.responder.apply_planned_path(before)
        return accepted, proposal

    def _record_bid(self, bid: Bid, accepted: bool, reason: str | None = None) -> None:
        hook = getattr(self.context.env, "telemetry_hook", None)
        if hook is None:
            return
        length = len(bid.proposed_path.points)
        hook.on_bid(OfferBidEvent(
            session_id=self.session.last_session_id, tick=self.context.tick,
            round_idx=self.session.last_session_rounds, agent_id=self.bidder.agent_id,
            path_length=length, path_heat=0.0, offered_utility=round(1.0 / max(1, length), 4),
            decision="ACCEPT" if accepted else "REJECT",
            reject_reason=reason or ("NONE" if accepted else "INSUFFICIENT_UTILITY")))

    def _record_impasse(self, bid: Bid) -> None:
        self.session.last_session_reason = "STATIONARY_IMPASSE"
        self._record_bid(bid, False, "STATIONARY_IMPASSE")
        logger.debug("Stationary impasse detected in session %s between %s and %s at round %d",
                     self.session.last_session_id, self.context.a.agent_id,
                     self.context.b.agent_id, self.session.last_session_rounds)

    def _settle(self, bid: Bid, response: Path) -> Contract | None:
        ctx = self.context
        if self.bidder.agent_id == ctx.a.agent_id:
            path_a, path_b, transfer = bid.proposed_path, response, bid.token_offered
        else:
            path_a, path_b, transfer = response, bid.proposed_path, -bid.token_offered
        tokens_a = getattr(ctx.a, "current_tokens", getattr(ctx.a, "tokens", 0))
        tokens_b = getattr(ctx.b, "current_tokens", getattr(ctx.b, "tokens", 0))
        if (transfer > 0 and tokens_a < transfer) or (transfer < 0 and tokens_b < -transfer):
            self.session.last_session_reason = "INSUFFICIENT_TOKENS"
            return None
        contract = Contract(session_id=self.session.last_session_id, agent_a=ctx.a.agent_id,
                            agent_b=ctx.b.agent_id, path_a=path_a, path_b=path_b,
                            token_transfer=transfer, timestamp=ctx.tick)
        if not validate_contract(contract, current_time=ctx.tick,
                                 disappear_at_target=ctx.env.config.setting.disappear_at_target):
            self.session.last_session_reason = "CONTRACT_VALIDATION_FAILED"
            return None
        settle_contract(ctx.a, ctx.b, contract, ctx.tick, verify_balances=False)
        self.session.check_deadline()
        self.session.last_session_reason = "NONE"
        return contract
