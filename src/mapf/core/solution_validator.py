"""Validate recorded grid paths independently of solver conflict detection.

Checks cover inputs, four-connected actions, arrival behavior and vertex/edge
collisions under Settings 1-4. Continuous dynamics are outside this grid model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mapf.core.models import Path, Point

if TYPE_CHECKING:
    from mapf.core.models import SimulationSetting
    from mapf.solvers.base import MAPFInstance


@dataclass(frozen=True)
class ValidationError:
    """Represents a physical or semantic violation in a MAPF solution."""

    error_type: str
    agent_a: str
    agent_b: str | None = None
    time_step: int | None = None
    location: tuple[int, int] | None = None
    details: str = ""

    def to_list(self) -> list[Any]:
        """Convert to list format compatible with audit probes."""
        res: list[Any] = [self.error_type, self.agent_a]
        if self.agent_b is not None:
            res.append(self.agent_b)
        if self.time_step is not None:
            res.append(self.time_step)
        if self.location is not None:
            res.append(list(self.location))
        return res


@dataclass
class ValidationResult:
    """Overall outcome of independent solution validation."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def error_summary(self) -> list[str]:
        return [
            f"[{e.error_type}] agent={e.agent_a}"
            + (f", peer={e.agent_b}" if e.agent_b else "")
            + (f", t={e.time_step}" if e.time_step is not None else "")
            + (f", loc={e.location}" if e.location is not None else "")
            for e in self.errors
        ]


Coordinate = tuple[int, int]


@dataclass
class _PathChecks:
    """Scenario and per-agent checks, independent of the solver's claims."""

    instance: MAPFInstance
    setting: SimulationSetting
    errors: list[ValidationError]

    def roster(self, paths: dict[str, Path]) -> None:
        if not self.instance.starts:
            self.errors.append(ValidationError("empty_roster", ""))
        for aid in sorted(set(self.instance.starts) ^ set(self.instance.goals)):
            self.errors.append(ValidationError("roster_mismatch", aid))
        for aid in sorted(paths.keys() - self.instance.starts.keys()):
            self.errors.append(ValidationError("unknown_agent", aid))

    def agent(self, aid: str, points: list[Coordinate]) -> None:
        if aid not in self.instance.goals:
            return
        if not points:
            self.errors.append(ValidationError("missing_path", aid))
            return
        start = self.instance.starts[aid]
        goal = self.instance.goals[aid]
        target = (goal.x, goal.y)
        if points[0] != (start.x, start.y):
            self.errors.append(ValidationError("wrong_start", aid, location=points[0]))
        if points[-1] != target:
            self.errors.append(ValidationError("wrong_goal", aid, location=points[-1]))
        for tick, point in enumerate(points):
            self.cell(aid, tick, point)
            if tick:
                self.transition(aid, tick, points[tick - 1], point)

    def cell(self, aid: str, tick: int, point: Coordinate) -> None:
        x, y = point
        inside = 0 <= x < self.instance.grid_width and 0 <= y < self.instance.grid_height
        if not inside:
            self.errors.append(ValidationError("out_of_bounds", aid, time_step=tick, location=point))
        if Point(x, y) in self.instance.obstacles:
            self.errors.append(ValidationError("obstacle", aid, time_step=tick, location=point))

    def transition(self, aid: str, tick: int, old: Coordinate, point: Coordinate) -> None:
        goal = self.instance.goals[aid]
        target = (goal.x, goal.y)
        distance = abs(point[0] - old[0]) + abs(point[1] - old[1])
        if distance > 1:
            self.errors.append(ValidationError("teleport", aid, time_step=tick, location=point))
        waiting_in_transit = distance == 0 and old != target
        if waiting_in_transit and not self.setting.allow_wait:
            self.errors.append(ValidationError("illegal_wait", aid, time_step=tick, location=point))
        if old == target and point != target:
            self.errors.append(ValidationError("departure_after_goal", aid, time_step=tick, location=point))


@dataclass
class _OccupancyTimeline:
    """Goal removal and indefinite occupancy of unfinished/parked path tails."""

    positions: dict[str, list[Coordinate]]
    arrivals: dict[str, int | None]
    disappear: bool

    @classmethod
    def from_paths(cls, instance: MAPFInstance, positions: dict[str, list[Coordinate]],
                   setting: SimulationSetting) -> _OccupancyTimeline:
        arrivals: dict[str, int | None] = {}
        for aid, points in positions.items():
            goal = instance.goals.get(aid)
            target = (goal.x, goal.y) if goal else None
            arrivals[aid] = points.index(target) if target in points else None
        return cls(positions, arrivals, setting.disappear_at_target)

    def at(self, aid: str, tick: int) -> Coordinate | None:
        points = self.positions.get(aid, [])
        arrival = self.arrivals.get(aid)
        after_arrival = arrival is not None and tick > arrival
        if self.disappear and after_arrival:
            return None
        if tick < len(points):
            return points[tick]
        return points[-1] if points else None

    def collisions(self, agents: list[str]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        previous: dict[str, Coordinate | None] = {}
        for tick in range(max((len(q) for q in self.positions.values()), default=0)):
            current = {aid: self.at(aid, tick) for aid in agents}
            errors.extend(_tick_collisions(tick, previous, current))
            previous = current
        return errors


def _tick_collisions(tick: int, previous: dict[str, Coordinate | None],
                     current: dict[str, Coordinate | None]) -> list[ValidationError]:
    """Index each occupied vertex and directed edge once; preserve diagnostic order."""
    errors: list[ValidationError] = []
    occupancy: dict[Coordinate, list[str]] = {}
    edges: dict[tuple[Coordinate, Coordinate], list[str]] = {}
    for aid, point in current.items():
        if point is None:
            continue
        errors.extend(ValidationError("vertex_collision", peer, aid, time_step=tick, location=point)
                      for peer in occupancy.get(point, []))
        occupancy.setdefault(point, []).append(aid)
        old = previous.get(aid)
        if old is not None and old != point:
            errors.extend(ValidationError("edge_collision", peer, aid, time_step=tick - 1, location=old)
                          for peer in edges.get((point, old), []))
            edges.setdefault((old, point), []).append(aid)
    return errors


def validate_solution(instance: MAPFInstance, paths: dict[str, Path],
                      setting: SimulationSetting) -> ValidationResult:
    """Verify roster, endpoints, map bounds, legal actions and space-time collisions.

    This checker uses recorded paths only. It never trusts solver success flags,
    reservation tables or conflict detectors, which may share a solver defect.
    """
    errors: list[ValidationError] = []
    checks = _PathChecks(instance, setting, errors)
    checks.roster(paths)
    positions = {aid: [(p.x, p.y) for p in path.points] for aid, path in paths.items()}
    for aid in instance.starts:
        checks.agent(aid, positions.get(aid, []))
    timeline = _OccupancyTimeline.from_paths(instance, positions, setting)
    errors.extend(timeline.collisions(list(instance.starts)))
    return ValidationResult(is_valid=not errors, errors=errors)
