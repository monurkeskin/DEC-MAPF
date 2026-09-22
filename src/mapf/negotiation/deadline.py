"""A monotonic deadline belongs to one bilateral session, never one offer."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


class NegotiationDeadlineExceeded(TimeoutError):
    """No agreement was committed inside this session's allowed interval."""


@dataclass(frozen=True)
class SessionDeadline:
    at: float | None
    clock: Callable[[], float] = time.monotonic

    def check(self) -> None:
        if self.at is not None and self.clock() >= self.at:
            raise NegotiationDeadlineExceeded("Bilateral negotiation deadline exhausted")
