from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from mapf.core.models import Bid, Conflict, Contract
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol, NegotiatorProtocol
from mapf.negotiation.contract import validate_contract
from mapf.negotiation.deadline import NegotiationDeadlineExceeded, SessionDeadline
from mapf.negotiation.ledger import restore_agent, snapshot_agent
from mapf.telemetry.events import OfferBidEvent

logger = logging.getLogger("mapf.negotiation")


class BilateralNegotiationSession(NegotiatorProtocol):
    """Versioned bilateral negotiation with one deadline per session.

    TAOP v2 requires a feasible concession or a new offer when a repeat is
    unaffordable. An unresolved session continues until its absolute deadline;
    the offer count is diagnostic. Earlier protocols retain their explicit
    token, offer or stationary-impasse termination rules for historical replay.
    These versions do not assert full equivalence to the published protocol.
    """

    def __init__(self, max_rounds: int = 30, protocol: str = "legacy-alternating-v1", *,
                 deadline_sec: float | None = None, clock: Callable[[], float] = time.monotonic,
                 sleeper: Callable[[float], None] = time.sleep,
                 lifecycle_hook: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.max_rounds = max_rounds
        self.protocol = protocol
        self.last_session_reason: str = "NONE"
        self.last_session_id: str = ""
        self.last_session_rounds: int = 1
        self.last_session_duration_sec: float = 0.0
        self.deadline_sec = 60.0 if protocol == "taop-v2" and deadline_sec is None else deadline_sec
        self.clock = clock
        self.sleeper = sleeper
        self.last_diagnostics: dict[str, Any] = {}
        self.lifecycle_hook = lifecycle_hook
        self._deadline = SessionDeadline(None, clock)

    def check_deadline(self) -> None:
        self._deadline.check()

    def progress(self, phase: str, **details: Any) -> None:
        self.check_deadline()
        self.last_diagnostics.update(phase=phase, round=self.last_session_rounds,
                                     observed_monotonic=self.clock(), **details)
        if self.lifecycle_hook is not None and self.protocol == "taop-v2":
            self.lifecycle_hook({"type": "negotiation_progress", "session_id": self.last_session_id,
                                 "diagnostics": self.last_diagnostics})

    def action(self, event: str, **details: Any) -> None:
        recent = self.last_diagnostics["recent_actions"]
        recent.append({"action": event, "round": self.last_session_rounds, **details})
        del recent[:-16]

    def pause_for_retry(self) -> None:
        self.progress("awaiting_legal_concession")
        remaining = max(0.0, (self._deadline.at or self.clock()) - self.clock())
        self.sleeper(min(.01, remaining))
        self.check_deadline()

    def negotiate(
        self,
        agent_a: AgentProtocol,
        agent_b: AgentProtocol,
        conflict: Conflict,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> Contract | None:
        session_id = f"nego-{uuid.uuid4().hex[:8]}"
        self.last_session_id = session_id
        self.last_session_reason = "NONE"
        self.last_session_rounds = 0

        started = self.clock()
        self.last_diagnostics = {
            "protocol": self.protocol, "tick": current_time, "phase": "snapshot",
            "started_monotonic": started, "observed_monotonic": started,
            "deadline_seconds": self.deadline_sec, "round": 0,
            "participants": [agent_a.agent_id, agent_b.agent_id],
            "token_balances": {agent_a.agent_id: agent_a.tokens, agent_b.agent_id: agent_b.tokens},
            "acknowledged_usage": {}, "unaffordable_repeats": 0, "concession_failures": 0,
            "offer_checkpoint_reached": False, "recent_actions": [],
            "search_expansion_limit": env.config.max_astar_expansions,
            "remaining_step_guard": max(0, env.config.max_steps - current_time),
        }
        self._deadline = SessionDeadline(
            None if self.deadline_sec is None else started + self.deadline_sec, self.clock)
        notify = self.lifecycle_hook if self.deadline_sec is not None else None
        if notify is not None:
            notify({"type": "negotiation_started", "session_id": session_id,
                    "tick": current_time, "deadline": self._deadline.at,
                    "diagnostics": self.last_diagnostics})
        before = None
        try:
            if self.deadline_sec is not None:
                before = (snapshot_agent(agent_a), snapshot_agent(agent_b))
            for agent in (agent_a, agent_b):
                vars(agent)["_active_negotiation_protocol"] = self.protocol
            self.check_deadline()
            return self._negotiate(agent_a, agent_b, conflict, env, current_time)
        except NegotiationDeadlineExceeded:
            if before is not None:
                restore_agent(agent_a, before[0])
                restore_agent(agent_b, before[1])
            self.last_session_reason = "NEGOTIATION_DEADLINE"
            self.last_settlement = None
            return None
        finally:
            self.last_session_duration_sec = self.clock() - started
            self.last_diagnostics.update(outcome=self.last_session_reason, elapsed_seconds=self.last_session_duration_sec)
            if notify is not None:
                notify({"type": "negotiation_finished", "session_id": session_id,
                        "reason": self.last_session_reason, "diagnostics": self.last_diagnostics})

    def _negotiate(self, agent_a: AgentProtocol, agent_b: AgentProtocol, conflict: Conflict,
                   env: EnvironmentProtocol, current_time: int) -> Contract | None:
        session_id = self.last_session_id

        if self.protocol == "taop-v2":
            from mapf.negotiation.taop_v2 import negotiate_taop_v2
            return negotiate_taop_v2(self, agent_a, agent_b, conflict, env, current_time)

        if self.protocol == "taop-v1":
            from mapf.negotiation.taop import negotiate_taop
            return negotiate_taop(self, agent_a, agent_b, conflict, env, current_time)

        # 1. Pre-negotiation hook
        agent_a.on_pre_negotiation(agent_b.agent_id, conflict, env, current_time)
        if hasattr(env, 'record_decision_heat'):
            env.record_decision_heat(agent_a, current_time, session_id)
        self.check_deadline()
        agent_b.on_pre_negotiation(agent_a.agent_id, conflict, env, current_time)
        if hasattr(env, 'record_decision_heat'):
            env.record_decision_heat(agent_b, current_time, session_id)
        self.check_deadline()

        # Configured max rounds cap
        effective_max_rounds = self.max_rounds

        # Determine bidding order: Agent A starts
        current_bidder = agent_a
        responder = agent_b
        last_bid: Bid | None = None

        # Track bid history per agent to detect concessions and stationary impasse
        last_bids: dict[str, Bid] = {}
        consecutive_stagnations: int = 0

        for round_num in range(1, effective_max_rounds + 1):
            self.check_deadline()
            self.last_session_rounds = round_num
            # Propose bid
            current_bid = current_bidder.make_bid(
                opponent_id=responder.agent_id,
                last_opponent_bid=last_bid,
                env=env,
                current_time=current_time,
                round_num=round_num,
            )
            self.check_deadline()

            # Check for concession relative to bidder's previous offer
            bidder_prev_bid = last_bids.get(current_bidder.agent_id)
            if bidder_prev_bid is not None:
                path_unchanged = (
                    current_bid.proposed_path == bidder_prev_bid.proposed_path
                )
                tokens_not_increased = (
                    current_bid.token_offered <= bidder_prev_bid.token_offered
                )

                if path_unchanged and tokens_not_increased:
                    # Current bidder made zero concession
                    consecutive_stagnations += 1
                else:
                    # Bidder made a genuine concession (changed path or escalated tokens)
                    consecutive_stagnations = 0

                # If BOTH agents consecutively make zero concession -> Stationary Impasse reached
                if consecutive_stagnations >= 2:
                    self.last_session_reason = "STATIONARY_IMPASSE"
                    hook = getattr(env, "telemetry_hook", None)
                    if hook is not None:
                        p_len = len(current_bid.proposed_path.points)
                        hook.on_bid(
                            OfferBidEvent(
                                session_id=session_id,
                                tick=current_time,
                                round_idx=round_num,
                                agent_id=current_bidder.agent_id,
                                path_length=p_len,
                                path_heat=0.0,
                                offered_utility=round(1.0 / max(1, p_len), 4),
                                decision="REJECT",
                                reject_reason="STATIONARY_IMPASSE",
                            )
                        )
                    logger.debug(
                        "Stationary impasse detected in session %s between %s and %s at round %d",
                        session_id,
                        agent_a.agent_id,
                        agent_b.agent_id,
                        round_num,
                    )
                    return None
            else:
                consecutive_stagnations = 0

            self.check_deadline()
            last_bids[current_bidder.agent_id] = current_bid

            # Legacy strategies propose by changing their own plan. Snapshot and restore
            # that proposal immediately so rejection/invalid contracts cannot commit it.
            before_response = responder.planned_path
            try:
                accepted = responder.evaluate_bid(
                    bid=current_bid,
                    env=env,
                    current_time=current_time,
                )
                response_proposal = responder.planned_path
            finally:
                if responder.planned_path != before_response:
                    responder.apply_planned_path(before_response)

            self.check_deadline()

            hook = getattr(env, "telemetry_hook", None)
            if hook is not None:
                p_len = len(current_bid.proposed_path.points)
                hook.on_bid(
                    OfferBidEvent(
                        session_id=session_id,
                        tick=current_time,
                        round_idx=round_num,
                        agent_id=current_bidder.agent_id,
                        path_length=p_len,
                        path_heat=0.0,
                        offered_utility=round(1.0 / max(1, p_len), 4),
                        decision="ACCEPT" if accepted else "REJECT",
                        reject_reason="NONE" if accepted else "INSUFFICIENT_UTILITY",
                    )
                )

            if accepted:
                # Construct contract
                if current_bidder.agent_id == agent_a.agent_id:
                    path_a = current_bid.proposed_path
                    path_b = response_proposal
                    transfer = current_bid.token_offered
                else:
                    path_a = response_proposal
                    path_b = current_bid.proposed_path
                    transfer = -current_bid.token_offered

                tokens_a = getattr(
                    agent_a, "current_tokens", getattr(agent_a, "tokens", 0)
                )
                tokens_b = getattr(
                    agent_b, "current_tokens", getattr(agent_b, "tokens", 0)
                )
                if (transfer > 0 and tokens_a < transfer) or (
                    transfer < 0 and tokens_b < -transfer
                ):
                    self.last_session_reason = "INSUFFICIENT_TOKENS"
                    return None

                contract = Contract(
                    session_id=session_id,
                    agent_a=agent_a.agent_id,
                    agent_b=agent_b.agent_id,
                    path_a=path_a,
                    path_b=path_b,
                    token_transfer=transfer,
                    timestamp=current_time,
                )

                # Final validation
                if validate_contract(
                    contract,
                    current_time=current_time,
                    disappear_at_target=env.config.setting.disappear_at_target,
                ):
                    from mapf.negotiation.ledger import settle_contract
                    settle_contract(agent_a, agent_b, contract, current_time, verify_balances=False)
                    self.check_deadline()
                    self.last_session_reason = "NONE"
                    return contract
                else:
                    self.last_session_reason = "CONTRACT_VALIDATION_FAILED"

            # Swap turns for next round
            last_bid = current_bid
            current_bidder, responder = responder, current_bidder

        self.last_session_reason = "MAX_ROUNDS_TIMEOUT"
        return None
