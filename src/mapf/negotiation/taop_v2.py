"""Token-limited insistence with legal concessions and one absolute deadline.

Article section 4 requires a new offer or a paid repeat. Java's run_concede
accepts a feasible opponent allocation. Search remains bounded, so inability to
construct a concession is logged and retried within the same session deadline.
"""
from typing import Any

from mapf.core.models import Bid, Conflict, Contract, Path
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol
from mapf.negotiation.agreement import admit_agreement
from mapf.negotiation.concession import feasible_concession, novel_offer
from mapf.negotiation.ledger import OfferLedger, restore_agent, snapshot_agent
from mapf.telemetry.events import OfferBidEvent


def negotiate_taop_v2(session: Any, a: AgentProtocol, b: AgentProtocol, conflict: Conflict,
                      env: EnvironmentProtocol, tick: int) -> Contract | None:
    ledger = OfferLedger()
    session.last_offer_ledger = ledger
    session.last_settlement = None
    local = {x.agent_id: env.for_agent(x.agent_id) if hasattr(env, "for_agent") else env for x in (a, b)}
    for agent, other in ((a, b), (b, a)):
        vars(agent)["_negotiation_reference_path"] = agent.planned_path
        vars(agent)["_acknowledged_usage"] = 0
        session.progress("prepare", agent=agent.agent_id)
        agent.on_pre_negotiation(other.agent_id, conflict, local[agent.agent_id], tick)
        if hasattr(env, 'record_decision_heat'):
            env.record_decision_heat(agent, tick, session.last_session_id)
        session.check_deadline()
    horizon = env.config.negotiation_horizon or env.config.fov_size
    def finite(offer: Bid | None) -> Bid | None:
        return None if offer is None else offer.model_copy(update={
            "proposed_path": Path(points=offer.proposed_path.points[:horizon])})
    offers: dict[str, Bid] = {}
    bidder, responder = a, b
    turn = 0
    while True:
        session.check_deadline()
        turn += 1
        session.last_session_rounds = turn
        session.last_diagnostics["offer_checkpoint_reached"] = turn >= session.max_rounds
        session.progress("proposal", agent=bidder.agent_id, acknowledged_usage=dict(ledger.usage))
        before = snapshot_agent(bidder)
        try:
            proposed = bidder.make_bid(responder.agent_id, finite(offers.get(responder.agent_id)),
                                       local[bidder.agent_id], tick, turn)
        finally:
            restore_agent(bidder, before)
        session.check_deadline()
        if proposed.bidder_id != bidder.agent_id:
            raise ValueError("TAOP bidder identity does not match the active participant")
        allocation = Path(points=proposed.proposed_path.points[:env.config.negotiation_horizon or env.config.fov_size])
        if not ledger.can_acknowledge(bidder.agent_id, allocation, bidder.tokens):
            session.last_diagnostics["unaffordable_repeats"] += 1
            opponent_offer = offers.get(responder.agent_id)
            if opponent_offer is not None:
                session.progress("forced_concession", agent=bidder.agent_id)
                finite_opponent = finite(opponent_offer)
                assert finite_opponent is not None
                response = feasible_concession(bidder, finite_opponent, local[bidder.agent_id], tick)
                session.check_deadline()
                session.action(response.reason, agent=bidder.agent_id, **response.components)
                if response.accepted:
                    session.progress("settlement", agent=bidder.agent_id)
                    contract = admit_agreement(session, a, b, responder, bidder, opponent_offer,
                                               response.proposed_path, conflict, env, tick, ledger)
                    if contract is not None:
                        return contract
                session.last_diagnostics["concession_failures"] += 1
            session.progress("novel_offer_search", agent=bidder.agent_id)
            alternative = novel_offer(bidder, ledger, local[bidder.agent_id], tick)
            session.check_deadline()
            if alternative is None:
                session.action("NO_NOVEL_OFFER_FOUND", agent=bidder.agent_id)
                session.pause_for_retry()
                bidder, responder = responder, bidder
                continue
            proposed = proposed.model_copy(update={"proposed_path": alternative})
            allocation = Path(points=alternative.points[:env.config.negotiation_horizon or env.config.fov_size])
        usage, repeated = ledger.acknowledge(bidder.agent_id, allocation, bidder.tokens)
        vars(bidder)["_acknowledged_usage"] = usage
        vars(bidder)["_negotiation_reference_path"] = proposed.proposed_path
        offers[bidder.agent_id] = proposed
        bid = proposed.model_copy(update={"token_offered": usage, "proposed_path": allocation})
        if hasattr(env, "deliver_message"):
            env.deliver_message(bidder.agent_id, responder.agent_id, allocation, "OFFER",
                                session_id=session.last_session_id, acknowledgement=usage)
        session.progress("response", agent=responder.agent_id, acknowledged_usage=dict(ledger.usage))
        before = snapshot_agent(responder)
        try:
            if hasattr(responder, "propose_response"):
                response = responder.propose_response(bid, local[responder.agent_id], tick)
            else:
                from mapf.core.models import BidDecision
                accepted = responder.evaluate_bid(bid, local[responder.agent_id], tick)
                response = BidDecision(accepted=accepted, proposed_path=responder.planned_path,
                                       reason="STRATEGY_ACCEPT" if accepted else "STRATEGY_REJECT")
        finally:
            restore_agent(responder, before)
        session.check_deadline()
        if not response.accepted and ledger.usage.get(responder.agent_id, 0) >= responder.tokens:
            session.progress("forced_concession", agent=responder.agent_id)
            response = feasible_concession(responder, bid, local[responder.agent_id], tick)
            session.check_deadline()
            if not response.accepted:
                session.last_diagnostics["concession_failures"] += 1
        session.action(response.reason, agent=responder.agent_id, **response.components)
        hook = getattr(env, "telemetry_hook", None)
        if hook is not None:
            hook.on_bid(OfferBidEvent(session_id=session.last_session_id, tick=tick, round_idx=turn,
                agent_id=bidder.agent_id, path_length=allocation.length, path_heat=None, offered_utility=None,
                decision="ACCEPT" if response.accepted else "REJECT", reject_reason=response.reason,
                utility_components={"responder": responder.agent_id, "response_evaluation": response.components},
                token_usage=usage, repeated_offer=repeated))
        if response.accepted:
            session.progress("settlement", agent=responder.agent_id)
            contract = admit_agreement(session, a, b, bidder, responder, proposed,
                                       response.proposed_path, conflict, env, tick, ledger)
            if contract is not None:
                return contract
            session.action("CONTRACT_VALIDATION_FAILED", agent=responder.agent_id)
        bidder, responder = responder, bidder
