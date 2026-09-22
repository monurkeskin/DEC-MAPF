from __future__ import annotations

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
        t = current_time + step
        vertex_occupancy: dict[Point, str] = {}
        edge_traversals: dict[tuple[Point, Point], str] = {}

        for a_id in agent_ids:
            p = paths[a_id]
            disappears = disappear_at_target and (
                goals is None or bool(p.points and p.points[-1] == goals[a_id])
            )
            pos = p.at_time(step, disappear_at_target=disappears)
            if pos is None:
                continue

            # 1. Vertex Conflict
            if pos in vertex_occupancy:
                other_agent = vertex_occupancy[pos]
                conflicts.append(
                    Conflict(
                        agent_a=other_agent,
                        agent_b=a_id,
                        time=t,
                        conflict_type=ConflictType.VERTEX,
                        location_a=pos,
                    )
                )
            else:
                vertex_occupancy[pos] = a_id

            # 2. Edge Swap Conflict (step -> step + 1)
            next_pos = p.at_time(step + 1, disappear_at_target=disappears)
            if step + 1 < end_t and next_pos is not None and pos != next_pos:
                rev_edge = (next_pos, pos)
                if rev_edge in edge_traversals:
                    other_agent = edge_traversals[rev_edge]
                    conflicts.append(
                        Conflict(
                            agent_a=other_agent,
                            agent_b=a_id,
                            time=t,
                            conflict_type=ConflictType.EDGE,
                            location_a=next_pos,
                            location_b=pos,
                        )
                    )
                edge_traversals[(pos, next_pos)] = a_id

    # Modern deterministic ordering; no archived partner-randomization equivalence.
    conflicts.sort(key=lambda c: (c.time, min(c.agent_a, c.agent_b), max(c.agent_a, c.agent_b)))
    return conflicts


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
