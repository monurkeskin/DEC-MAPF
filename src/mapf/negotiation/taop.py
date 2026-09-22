"""Versioned article-prose TAOP; bounded path generators remain modern variants."""

from __future__ import annotations

from typing import Any

from mapf.agents.base import BaseAgent
from mapf.core.models import Conflict, Contract, Path
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol
from mapf.core.solution_validator import validate_solution
from mapf.negotiation.ledger import (
    OfferLedger,
    restore_agent,
    settle_contract,
    snapshot_agent,
)
from mapf.solvers.base import MAPFInstance
from mapf.telemetry.events import OfferBidEvent


def negotiate_taop(
    session: Any, a: AgentProtocol, b: AgentProtocol, conflict: Conflict,
    env: EnvironmentProtocol, tick: int,
) -> Contract | None:
    ledger = OfferLedger()
    session.last_offer_ledger = ledger
    session.last_settlement = None
    environments = {
        agent.agent_id: env.for_agent(agent.agent_id) if hasattr(env, "for_agent") else env
        for agent in (a, b)
    }
    for agent, opponent in ((a, b), (b, a)):
        vars(agent)["_negotiation_reference_path"] = agent.planned_path
        vars(agent)["_acknowledged_usage"] = 0
        agent.on_pre_negotiation(opponent.agent_id, conflict, environments[agent.agent_id], tick)
        if hasattr(env, 'record_decision_heat'):
            env.record_decision_heat(agent, tick, session.last_session_id)
        session.check_deadline()
    bidder, responder = a, b
    last_bid = None
    for turn in range(1, session.max_rounds + 1):
        session.check_deadline()
        session.last_session_rounds = turn
        # Proposal generation cannot commit plans, balances or strategy extension state.
        before = snapshot_agent(bidder)
        try:
            proposed = bidder.make_bid(responder.agent_id, last_bid,
                                       environments[bidder.agent_id], tick, turn)
        finally:
            restore_agent(bidder, before)
        session.check_deadline()
        horizon = env.config.negotiation_horizon or env.config.fov_size
        allocation = Path(points=proposed.proposed_path.points[:horizon])
        if proposed.bidder_id != bidder.agent_id:
            session.last_session_reason = "WRONG_BIDDER"
            return None
        try:
            usage, repeated = ledger.acknowledge(bidder.agent_id, allocation, bidder.tokens)
        except ValueError:
            session.last_session_reason = "TOKEN_EXHAUSTED"
            return None
        # The acknowledgement is cumulative usage; final transfer is its positive difference.
        bid = proposed.model_copy(update={"token_offered": usage, "proposed_path": allocation})
        vars(bidder)["_acknowledged_usage"] = usage
        vars(bidder)["_negotiation_reference_path"] = proposed.proposed_path
        if hasattr(env, "deliver_message"):
            env.deliver_message(bidder.agent_id, responder.agent_id, allocation, "OFFER",
                                session_id=session.last_session_id, acknowledgement=usage)
        # BaseAgent's public pure bridge already performs a complete transaction.
        # Keep the outer guard for arbitrary plugin overrides and legacy callbacks.
        pure_bridge = getattr(getattr(responder, "propose_response", None), "__func__", None) is BaseAgent.propose_response
        response_snapshot = None if pure_bridge else snapshot_agent(responder)
        try:
            if hasattr(responder, "propose_response"):
                proposal = responder.propose_response(bid, environments[responder.agent_id], tick)
                accepted, response_path, decision = proposal.accepted, proposal.proposed_path, proposal.components
            else:
                accepted = responder.evaluate_bid(bid, environments[responder.agent_id], tick)
                response_path = responder.planned_path.model_copy(deep=True)
                decision = dict(getattr(responder, "_last_decision", {}))
        finally:
            if response_snapshot is not None:
                restore_agent(responder, response_snapshot)
        session.check_deadline()
        hook = getattr(env, "telemetry_hook", None)
        if hook is not None:
            hook.on_bid(OfferBidEvent(
                session_id=session.last_session_id, tick=tick, round_idx=turn,
                agent_id=bidder.agent_id, path_length=allocation.length,
                path_heat=None, offered_utility=None,
                decision="ACCEPT" if accepted else "REJECT",
                reject_reason=decision.get("reason", "STRATEGY_ACCEPT" if accepted else "STRATEGY_REJECT"),
                utility_components={"responder": responder.agent_id, "response_evaluation": decision},
                token_usage=usage, repeated_offer=repeated,
            ))
        if accepted:
            transfer = ledger.payment(bidder.agent_id, responder.agent_id)
            paths = {bidder.agent_id: proposed.proposed_path, responder.agent_id: response_path}
            instance = MAPFInstance(
                starts={x.agent_id: x.current_pos for x in (a, b)},
                goals={x.agent_id: x.target_pos for x in (a, b)},
                grid_width=env.config.grid_width, grid_height=env.config.grid_height,
                obstacles=env.config.obstacles,
            )
            # The agreed finite allocation must be respected. Full current plans are
            # independently checked too; admission never blesses a teleport or wrong goal.
            validation = validate_solution(instance, paths, env.config.setting)
            relevant_errors = [e for e in validation.errors if not (
                e.error_type in ("vertex_collision", "edge_collision")
                and e.time_step is not None and e.time_step >= len(allocation.points) - (e.error_type == "edge_collision")
            )]
            prior_obligation_broken = any(
                isinstance(agent, BaseAgent) and not agent.respects_commitments(
                    paths[agent.agent_id], tick, stay_at_goal=not env.config.setting.disappear_at_target
                ) for agent in (a, b)
            )
            if relevant_errors or prior_obligation_broken:
                session.last_session_reason = "CONTRACT_VALIDATION_FAILED"
            else:
                contract = Contract(
                    session_id=session.last_session_id, agent_a=a.agent_id, agent_b=b.agent_id,
                    path_a=paths[a.agent_id], path_b=paths[b.agent_id],
                    token_transfer=transfer if bidder is a else -transfer, timestamp=tick,
                    accepted_by=responder.agent_id, allocated_path=allocation,
                    conflict_tick=conflict.end_time, token_usage=dict(ledger.usage), protocol_version="taop-v1",
                )
                session.check_deadline()
                session.last_settlement = settle_contract(a, b, contract, tick)
                session.check_deadline()
                if hasattr(env, "record_settlement"):
                    env.record_settlement(session.last_settlement)
                session.last_session_reason = "AGREED"
                return contract
        last_bid = bid
        bidder, responder = responder, bidder
    session.last_session_reason = "ROUND_BUDGET_EXHAUSTED"
    return None
