"""Tiny exhaustive oracle using tuples only, independent of production MAPF code.

Retains the joint-state Dijkstra objective and physical witnesses used in the
two-agent 2x2 qualification. This is deliberately not the production validator.
"""

import heapq
import itertools


def _choices(point, goal, size, setting):
    if point is None:
        return [None]
    if point == goal:
        return [None] if setting.disappear_at_target else [goal]
    x, y = point
    candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    if setting.allow_wait:
        candidates.append(point)
    return [(a, b) for a, b in candidates if 0 <= a < size and 0 <= b < size]


def _legal_transition(state, next_state):
    a, b = next_state
    if a is not None and a == b:
        return False
    if None in next_state:
        return True
    swap = a == state[1] and b == state[0]
    return not (swap and a != b)


def _unfinished(state, goals):
    return sum(p is not None and p != g for p, g in zip(state, goals, strict=True))


def optimal_joint_cost(starts, goals, size, setting):
    counter = itertools.count()
    heap = [(0, next(counter), starts)]
    best = {starts: 0}
    while heap:
        cost, _, state = heapq.heappop(heap)
        if cost != best[state]:
            continue
        unfinished = _unfinished(state, goals)
        if not unfinished:
            return cost
        choices = [_choices(p, g, size, setting) for p, g in zip(state, goals, strict=True)]
        for nxt in itertools.product(*choices):
            value = cost + unfinished
            if _legal_transition(state, nxt) and value < best.get(nxt, 10**6):
                best[nxt] = value
                heapq.heappush(heap, (value, next(counter), nxt))
    return None


def _assert_track(track, start, goal, setting):
    assert track[0] == start and track[-1] == goal
    for old, new in itertools.pairwise(track):
        distance = abs(old[0] - new[0]) + abs(old[1] - new[1])
        valid_wait = distance == 0 and (setting.allow_wait or old == goal)
        assert distance == 1 or valid_wait
        if old == goal:
            assert new == old


def _position(track, tick, setting):
    if tick < len(track):
        return track[tick]
    return None if setting.disappear_at_target else track[-1]


def _assert_separation(tracks, setting):
    for tick in range(max(map(len, tracks.values()))):
        p = [_position(tracks[a], tick, setting) for a in ("a", "b")]
        assert p[0] is None or p[0] != p[1]
        if tick and None not in p:
            old_b = tracks["b"][min(tick - 1, len(tracks["b"]) - 1)]
            old_a = tracks["a"][min(tick - 1, len(tracks["a"]) - 1)]
            assert not (p[0] == old_b and p[1] == old_a)


def assert_physical_paths(tracks, starts, goals, setting):
    for i, aid in enumerate(("a", "b")):
        _assert_track(tracks[aid], starts[i], goals[i], setting)
    _assert_separation(tracks, setting)
