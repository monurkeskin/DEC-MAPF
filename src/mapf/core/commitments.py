"""Immutable opponent reservations with explicit absolute time and ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mapf.core.models import Path, Point
from mapf.core.space_time_grid import ReservationTable


@dataclass(frozen=True)
class CommitmentReservation:
    contract_id: str
    owner_id: str
    opponent_id: str
    start_tick: int
    points: tuple[Point, ...]
    policy: str

    @property
    def end_tick(self) -> int:
        return self.start_tick + len(self.points) - 1

    def is_active(self, current_tick: int) -> bool:
        """ZC releases after the agreement tick's move, not during negotiation.

        Its entire offered allocation constrains decisions in that tick. SC/DC
        instead retain their (possibly truncated) allocation until its last state.
        """
        return current_tick <= self.end_tick and (
            self.policy != "ZC" or current_tick <= self.start_tick
        )

    def add_to(self, table: ReservationTable, current_tick: int) -> None:
        if not self.is_active(current_tick):
            return
        for i, point in enumerate(self.points):
            tick = self.start_tick + i
            if tick >= current_tick:
                table.reserve_vertex(self.opponent_id, point, tick)
            if i + 1 < len(self.points) and tick >= current_tick:
                table.reserve_edge(self.opponent_id, point, self.points[i + 1], tick)

    def conflicts_with(self, path: Path, current_tick: int, *, stay_at_goal: bool) -> bool:
        """Check a proposed plan against this live promise, including goal occupancy."""
        if not self.is_active(current_tick):
            return False
        for i, point in enumerate(self.points):
            relative_tick = self.start_tick + i - current_tick
            if relative_tick < 0:
                continue
            position = path.at_time(relative_tick, disappear_at_target=not stay_at_goal)
            if point == position:
                return True
            if i + 1 < len(self.points) and self.points[i + 1] == position:
                after = path.at_time(relative_tick + 1, disappear_at_target=not stay_at_goal)
                if point == after:
                    return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "owner_id": self.owner_id,
            "opponent_id": self.opponent_id,
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
            "policy": self.policy,
            "role": "avoid opponent vertex and reverse-edge occupancy",
            "release": "after agreement-tick movement" if self.policy == "ZC" else "after end_tick",
            "expires_at_tick": self.start_tick + 1 if self.policy == "ZC" else self.end_tick + 1,
            "points": [[p.x, p.y] for p in self.points],
        }
