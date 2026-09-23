"""Parent-side hard deadline for one currently active negotiation."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NegotiationWatch:
    session_id: str | None = None
    deadline: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def receive(self, event: dict[str, Any]) -> None:
        if event.get("type") == "negotiation_started":
            if self.session_id is not None:
                raise ValueError("Overlapping negotiation deadline notifications")
            session_id = event.get("session_id")
            deadline = event.get("deadline")
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("Missing negotiation deadline identity")
            if not isinstance(deadline, (int, float)) or isinstance(deadline, bool) or not math.isfinite(deadline):
                raise ValueError("Invalid negotiation deadline")
            diagnostics = event.get("diagnostics", {})
            if not isinstance(diagnostics, dict):
                raise ValueError("Malformed negotiation start diagnostics")
            self.session_id, self.deadline = session_id, deadline
            self.diagnostics = dict(diagnostics)
        elif event.get("type") == "negotiation_progress":
            if self.session_id is None or event.get("session_id") != self.session_id:
                raise ValueError("Stale negotiation progress")
            details = event.get("diagnostics")
            if not isinstance(details, dict):
                raise ValueError("Malformed negotiation progress")
            self.diagnostics = dict(details)
        elif event.get("type") == "negotiation_finished":
            if self.session_id is None or event.get("session_id") != self.session_id:
                raise ValueError("Stale negotiation deadline completion")
            self.session_id, self.deadline = None, None
        else:
            raise ValueError("Unknown worker deadline notification")

    def expired(self, now: float) -> bool:
        return self.deadline is not None and now >= self.deadline

    def timeout_diagnostics(self, now: float) -> dict[str, Any]:
        observed = self.diagnostics.get("observed_monotonic")
        return {**self.diagnostics, "session_id": self.session_id, "deadline_monotonic": self.deadline,
                "supervisor_observed_monotonic": now,
                "seconds_since_progress": max(0.0, now - observed) if isinstance(observed, (int, float)) else None,
                "scope": "Last worker observation before hard termination; no unobserved phase is inferred"}
