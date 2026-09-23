"""Incremental occupancy index with the full detector's ordering and semantics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from mapf.core.models import Conflict, Path, Point
from mapf.negotiation._conflict_occupancy import ConflictOccupancy
from mapf.negotiation.conflict import detect_conflicts


@dataclass(frozen=True, slots=True)
class _PlanChanges:
    replaced: int
    removed: int
    context_changed: bool

    @property
    def unchanged(self) -> bool:
        return self.replaced == self.removed == 0 and not self.context_changed

    def requires_scan(self, roster_size: int) -> bool:
        if self.context_changed or roster_size < 16:
            return True
        return self.replaced + self.removed > roster_size // 2


class ConflictIndex:
    """Cache unchanged plans; update occupancy only for sparse roster changes.

    Identity checks cover custom agents that replace plans without notifying the
    engine. Retained immutable paths prevent object-id reuse. Dense changes use
    the reference scan, avoiding the higher cost of rebuilding every bucket.
    """

    def __init__(self) -> None:
        self.stats: Counter[str] = Counter()
        self._input_paths: dict[str, Path] = {}
        self._input_goals: dict[str, Point] | None = None
        self._input_shape: tuple[int, bool] | None = None
        self._relative_conflicts: tuple[Conflict, ...] = ()
        self._occupancy = ConflictOccupancy(self.stats)

    def detect(
        self,
        paths: dict[str, Path],
        current_time: int = 0,
        lookahead_steps: int = 20,
        disappear_at_target: bool = False,
        goals: dict[str, Point] | None = None,
    ) -> list[Conflict]:
        context = (lookahead_steps, disappear_at_target)
        current_goals = goals if disappear_at_target else None
        changes = _PlanChanges(
            sum(self._input_paths.get(aid) is not path for aid, path in paths.items()),
            len(self._input_paths.keys() - paths.keys()),
            context != self._input_shape or current_goals != self._input_goals,
        )
        if changes.unchanged:
            self.stats["result_hits"] += 1
        else:
            self._refresh(paths, context, current_goals, changes)
        if current_time == 0:
            return list(self._relative_conflicts)
        return [
            c.model_copy(update={"time": c.time + current_time})
            for c in self._relative_conflicts
        ]

    def _refresh(
        self,
        paths: dict[str, Path],
        context: tuple[int, bool],
        goals: dict[str, Point] | None,
        changes: _PlanChanges,
    ) -> None:
        self.stats["path_updates"] += changes.replaced
        self.stats["path_removals"] += changes.removed
        horizon, disappears = context
        if changes.requires_scan(len(paths)):
            conflicts = detect_conflicts(paths, 0, horizon, disappears, goals)
            self._occupancy.invalidate()
            self.stats["full_scans"] += 1
        else:
            conflicts = self._occupancy.detect(paths, horizon, disappears, goals)
            self.stats["incremental_queries"] += 1
        self._relative_conflicts = tuple(conflicts)
        self._input_paths = dict(paths)
        self._input_goals = dict(goals) if goals is not None else None
        self._input_shape = context
