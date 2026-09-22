"""Online accounting from actual delivery receipts, independent of trace recording."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from mapf.core.models import Point
from mapf.core.observations import Message


class CommunicationLedger:
    def __init__(self) -> None:
        self.spatial: dict[tuple[str, str], set[tuple[int, int]]] = defaultdict(set)
        self.spacetime: dict[tuple[str, str], set[tuple[int, int, int]]] = defaultdict(set)
        self.messages = 0
        self.bytes = 0
        self.cells = 0
        self.transferred = 0
        self.transfers = 0
        self.broadcast_pairs: set[tuple[str, str]] = set()
        self.broadcast_spatial: dict[tuple[str, str], set[tuple[int, int]]] = defaultdict(set)

    def deliver(self, message: Message) -> None:
        key = (message.sender, message.recipient)
        self.spatial[key].update(message.points)
        self.spacetime[key].update((message.tick + i, x, y) for i, (x, y) in enumerate(message.points))
        self.messages += 1
        self.bytes += message.payload_bytes
        self.cells += len(message.points)
        if message.kind == "BROADCAST":
            self.broadcast_pairs.add(key)
            self.broadcast_spatial[key].update(message.points)

    def transfer(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Transfer volume must be nonnegative")
        self.transferred += amount
        self.transfers += int(amount > 0)

    def metrics(self, paths: dict[str, list[Point]], balances: dict[str, int]) -> dict[str, Any]:
        ids = list(paths)
        spatial, temporal, broadcast = 0.0, 0.0, 0.0
        for sender in ids:
            points = {(p.x, p.y) for p in paths[sender]}
            times = {(t, p.x, p.y) for t, p in enumerate(paths[sender])}
            for recipient in ids:
                if sender != recipient:
                    spatial += len(points & self.spatial.get((sender, recipient), set())) / max(1, len(points))
                    broadcast += len(points & self.broadcast_spatial.get((sender, recipient), set())) / max(1, len(points))
                    temporal += len(times & self.spacetime.get((sender, recipient), set())) / max(1, len(times))
        denominator = max(1, len(ids) * (len(ids) - 1))
        values = [balances[a] for a in ids]
        total = sum(values)
        gini = (sum(abs(a-b) for a in values for b in values) / (2 * len(values) * total)
                if values and total else 0.0)
        return {
            "metric_version": "delivered-metrics-v2",
            "information_sharing_rate": broadcast / denominator,
            "all_message_information_sharing_rate": spatial / denominator,
            "spacetime_information_sharing_rate": temporal / denominator,
            "information_sharing_definition": "delivered BROADCAST spatial set intersection; repeats collapse; all ordered recipient pairs",
            "message_count": self.messages, "payload_bytes": self.bytes,
            "transmitted_cells": self.cells, "token_exchanges": self.transferred,
            "transfer_count": self.transfers, "final_token_balances": balances,
            "token_gini": gini, "broadcast_ratio": len(self.broadcast_pairs) / denominator,
        }
