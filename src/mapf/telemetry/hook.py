"""Telemetry Hook Interfaces for Zero-Overhead Simulation Instrumentation.

Provides an abstract interface, a zero-cost NullTelemetryHook for production
runs where telemetry is disabled, and an asynchronous QueuedTelemetryHook that
dispatches discrete events to an in-memory queue.
"""

from __future__ import annotations

import queue
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from mapf.telemetry.events import (
    AgentMoveEvent,
    BroadcastEvent,
    KeyframeEvent,
    ManifestEvent,
    NegotiationSessionEvent,
    OfferBidEvent,
)
from mapf.telemetry.schema import SerializableEvent


@runtime_checkable
class TelemetryHook(Protocol):
    """Protocol defining hooks for discrete simulation event emission."""

    def on_manifest(self, event: ManifestEvent) -> None:
        """Record the initial run provenance manifest."""
        ...

    def on_diagnostic(self, event: Any) -> None: ...

    def on_keyframe(self, event: KeyframeEvent) -> None:
        """Record a periodic full-state keyframe snapshot."""
        ...

    def on_move(self, event: AgentMoveEvent) -> None:
        """Record an agent step or wait action."""
        ...

    def on_bid(self, event: OfferBidEvent) -> None:
        """Record an individual bid or counter-bid."""
        ...

    def on_negotiation_end(self, event: NegotiationSessionEvent) -> None:
        """Record the outcome of a bilateral negotiation session."""
        ...

    def on_broadcast(self, event: BroadcastEvent) -> None:
        """Record a spatial broadcast."""
        ...


class NullTelemetryHook:
    """Zero-overhead dummy hook. All methods are no-ops."""

    __slots__ = ()

    def on_diagnostic(self, event: Any) -> None:
        pass

    def on_manifest(self, event: ManifestEvent) -> None:
        pass

    def on_keyframe(self, event: KeyframeEvent) -> None:
        pass

    def on_move(self, event: AgentMoveEvent) -> None:
        pass

    def on_bid(self, event: OfferBidEvent) -> None:
        pass

    def on_negotiation_end(self, event: NegotiationSessionEvent) -> None:
        pass

    def on_broadcast(self, event: BroadcastEvent) -> None:
        pass


class QueuedTelemetryHook:
    """Pushes discrete telemetry events into an asynchronous in-memory queue."""

    __slots__ = ("_emit",)

    def __init__(self, event_queue: queue.SimpleQueue[Any] | None = None,
                 *, emit: Callable[[SerializableEvent], None] | None = None) -> None:
        if emit is None and event_queue is None:
            raise ValueError("An event sink is required")
        self._emit = emit if emit is not None else event_queue.put_nowait  # type: ignore[union-attr]

    def on_manifest(self, event: ManifestEvent) -> None:
        self._emit(event)

    def on_diagnostic(self, event: Any) -> None:
        self._emit(event)

    def on_keyframe(self, event: KeyframeEvent) -> None:
        self._emit(event)

    def on_move(self, event: AgentMoveEvent) -> None:
        self._emit(event)

    def on_bid(self, event: OfferBidEvent) -> None:
        self._emit(event)

    def on_negotiation_end(self, event: NegotiationSessionEvent) -> None:
        self._emit(event)

    def on_broadcast(self, event: BroadcastEvent) -> None:
        self._emit(event)
