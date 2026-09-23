from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from mapf.core.models import Conflict, Contract
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol, NegotiatorProtocol
from mapf.negotiation.deadline import NegotiationDeadlineExceeded, SessionDeadline
from mapf.negotiation.ledger import restore_agent, snapshot_agent


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
        except Exception as exc:
            self.last_session_reason = "NEGOTIATION_ERROR"
            self.last_diagnostics["error_type"] = type(exc).__name__
            raise
        finally:
            self.last_session_duration_sec = self.clock() - started
            self.last_diagnostics.update(outcome=self.last_session_reason, elapsed_seconds=self.last_session_duration_sec)
            if notify is not None:
                notify({"type": "negotiation_finished", "session_id": session_id,
                        "reason": self.last_session_reason, "diagnostics": self.last_diagnostics})

    def _negotiate(self, agent_a: AgentProtocol, agent_b: AgentProtocol, conflict: Conflict,
                   env: EnvironmentProtocol, current_time: int) -> Contract | None:
        if self.protocol == "taop-v2":
            from mapf.negotiation.taop_v2 import negotiate_taop_v2
            return negotiate_taop_v2(self, agent_a, agent_b, conflict, env, current_time)

        if self.protocol == "taop-v1":
            from mapf.negotiation.taop import negotiate_taop
            return negotiate_taop(self, agent_a, agent_b, conflict, env, current_time)

        from mapf.negotiation._context import NegotiationContext
        from mapf.negotiation._legacy_alternating import LegacyAlternating
        return LegacyAlternating(NegotiationContext(self, agent_a, agent_b, conflict, env, current_time)).run()
