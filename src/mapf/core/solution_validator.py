"""Independent solution validator for multi-agent path finding solutions.

Provides decoupled, objective verification of physical space-time validity,
kinodynamics, goal reachability, and collision-free invariants across all
simulation settings (Settings 1-4, DaT vs noDaT, allow_wait).
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


def validate_solution(
    instance: MAPFInstance,
    paths: dict[str, Path],
    setting: SimulationSetting,
) -> ValidationResult:
    """Validate executed or planned paths independently of solver internals.

    Verifies:
    1. Completeness: every agent has an executed path.
    2. Boundary conditions: starts at designated start, ends at designated goal.
    3. Grid constraints: all coordinates are within grid bounds and never on static obstacles.
    4. Kinodynamics: steps are adjacent (Manhattan distance <= 1).
    5. Setting rules: if allow_wait is False, stationary waits before the goal are forbidden.
    6. Vertex collisions: no two active/parked agents occupy the same cell at time t.
    7. Edge collisions: no two agents cross each other on the same edge at t -> t+1.
    """
    errors: list[ValidationError] = []

    if not instance.starts:
        errors.append(ValidationError("empty_roster", ""))
    for a in sorted(set(instance.starts) ^ set(instance.goals)):
        errors.append(ValidationError("roster_mismatch", a))
    for a in sorted(paths.keys() - instance.starts.keys()):
        errors.append(ValidationError("unknown_agent", a))

    pos_dict: dict[str, list[tuple[int, int]]] = {
        a: [(p.x, p.y) for p in path.points] for a, path in paths.items()
    }

    # 1. Per-agent boundary, obstacle, and kinodynamic checks
    for a in instance.starts:
        if a not in instance.goals:
            continue
        q = pos_dict.get(a, [])
        if not q:
            errors.append(ValidationError("missing_path", a))
            continue

        start_pt = (instance.starts[a].x, instance.starts[a].y)
        goal_pt = (instance.goals[a].x, instance.goals[a].y)

        if q[0] != start_pt:
            errors.append(ValidationError("wrong_start", a, location=q[0]))
        if q[-1] != goal_pt:
            errors.append(ValidationError("wrong_goal", a, location=q[-1]))

        for t, (x, y) in enumerate(q):
            if not (0 <= x < instance.grid_width and 0 <= y < instance.grid_height):
                errors.append(
                    ValidationError("out_of_bounds", a, time_step=t, location=(x, y))
                )
            if Point(x, y) in instance.obstacles:
                errors.append(
                    ValidationError("obstacle", a, time_step=t, location=(x, y))
                )

            if t > 0:
                dist = abs(x - q[t - 1][0]) + abs(y - q[t - 1][1])
                if dist > 1:
                    errors.append(
                        ValidationError("teleport", a, time_step=t, location=(x, y))
                    )
                if dist == 0 and not setting.allow_wait and q[t - 1] != goal_pt:
                    errors.append(
                        ValidationError("illegal_wait", a, time_step=t, location=(x, y))
                    )
                if q[t - 1] == goal_pt and (x, y) != goal_pt:
                    errors.append(
                        ValidationError(
                            "departure_after_goal", a, time_step=t, location=(x, y)
                        )
                    )

    # 2. Index occupancy and directed transitions once per tick: O(k*T + violations).
    # Arrival is computed once, rather than scanning a path inside each pairwise check.
    arrivals: dict[str, int | None] = {}
    for aid, q in pos_dict.items():
        goal = instance.goals.get(aid)
        target = (goal.x, goal.y) if goal else None
        arrivals[aid] = q.index(target) if target in q else None

    def at(agent_id: str, t: int) -> tuple[int, int] | None:
        q = pos_dict.get(agent_id, [])
        arrival = arrivals.get(agent_id)
        if setting.disappear_at_target and arrival is not None and t > arrival:
            return None
        if t < len(q):
            return q[t]
        # An incomplete path never disappears merely because its recording ended.
        return q[-1] if q else None

    agents = list(instance.starts)
    max_t = max((len(q) for q in pos_dict.values()), default=0)
    previous: dict[str, tuple[int, int] | None] = {}
    for t in range(max_t):
        occupancy: dict[tuple[int, int], list[str]] = {}
        edges: dict[tuple[tuple[int, int], tuple[int, int]], list[str]] = {}
        current = {a: at(a, t) for a in agents}
        for a, point in current.items():
            if point is None:
                continue
            for b in occupancy.get(point, []):
                errors.append(
                    ValidationError(
                        "vertex_collision", b, a, time_step=t, location=point
                    )
                )
            occupancy.setdefault(point, []).append(a)
            old = previous.get(a)
            if old is not None and old != point:
                for b in edges.get((point, old), []):
                    errors.append(
                        ValidationError(
                            "edge_collision", b, a, time_step=t - 1, location=old
                        )
                    )
                edges.setdefault((old, point), []).append(a)
        previous = current

    return ValidationResult(is_valid=(len(errors) == 0), errors=errors)
