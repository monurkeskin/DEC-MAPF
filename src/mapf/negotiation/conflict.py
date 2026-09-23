from __future__ import annotations

from dataclasses import dataclass, field

from mapf.core.models import Conflict, ConflictType, Path, Point


def detect_conflicts(
    paths: dict[str, Path],
    current_time: int = 0,
    lookahead_steps: int = 20,
    disappear_at_target: bool = False,
    goals: dict[str, Point] | None = None,
) -> list[Conflict]:
    """Check states t=0..lookahead_steps and edges contained in that action horizon.

    Supply goals for potentially incomplete plans: a truncated non-goal plan
    retains its last occupied cell. Without goals, callers promise complete paths.
    """
    conflicts: list[Conflict] = []
    agent_ids = sorted(paths.keys())
    if len(agent_ids) < 2:
        return conflicts

    max_len = max((len(paths[aid].points) for aid in agent_ids), default=0)
    end_t = min(max_len, lookahead_steps + 1)

    for step in range(end_t):
        occupancy = _TickOccupancy(step, current_time + step, step + 1 < end_t, conflicts)
        for a_id in agent_ids:
            path = paths[a_id]
            occupancy.record(a_id, path, _disappears(path, a_id, goals, disappear_at_target))

    # Modern deterministic ordering; no archived partner-randomization equivalence.
    conflicts.sort(key=lambda c: (c.time, min(c.agent_a, c.agent_b), max(c.agent_a, c.agent_b)))
    return conflicts


def _disappears(path: Path, agent: str, goals: dict[str, Point] | None, enabled: bool) -> bool:
    if not enabled:
        return False
    if goals is None:
        return True
    return bool(path.points and path.points[-1] == goals[agent])


@dataclass
class _TickOccupancy:
    step: int
    time: int
    inspect_edge: bool
    conflicts: list[Conflict]
    vertices: dict[Point, str] = field(default_factory=dict)
    edges: dict[tuple[Point, Point], str] = field(default_factory=dict)

    def record(self, agent: str, path: Path, disappears: bool) -> None:
        position = path.at_time(self.step, disappear_at_target=disappears)
        if position is None:
            return
        self._vertex(agent, position)
        following = path.at_time(self.step + 1, disappear_at_target=disappears)
        if self.inspect_edge and following is not None:
            self._edge(agent, position, following)

    def _vertex(self, agent: str, position: Point) -> None:
        if position in self.vertices:
            self.conflicts.append(Conflict(agent_a=self.vertices[position], agent_b=agent,
                time=self.time, conflict_type=ConflictType.VERTEX, location_a=position))
        else:
            self.vertices[position] = agent

    def _edge(self, agent: str, position: Point, following: Point) -> None:
        if position == following:
            return
        reverse = (following, position)
        if reverse in self.edges:
            self.conflicts.append(Conflict(agent_a=self.edges[reverse], agent_b=agent,
                time=self.time, conflict_type=ConflictType.EDGE,
                location_a=following, location_b=position))
        self.edges[(position, following)] = agent


def find_first_conflict(
    paths: dict[str, Path],
    current_time: int = 0,
    lookahead_steps: int = 20,
    disappear_at_target: bool = False,
) -> Conflict | None:
    """Returns earliest conflict in space-time if one exists."""
    all_conflicts = detect_conflicts(
        paths=paths,
        current_time=current_time,
        lookahead_steps=lookahead_steps,
        disappear_at_target=disappear_at_target,
    )
    if not all_conflicts:
        return None
    # Sort by earliest conflict time
    return min(all_conflicts, key=lambda c: c.time)
