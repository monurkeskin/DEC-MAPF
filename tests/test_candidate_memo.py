"""Exact memo boundaries: changes in geometry, reservations and budgets stay visible."""

import pytest

from mapf.core.models import Point
from mapf.core.space_time_grid import (
    CandidateSearchCache,
    ReservationTable,
    SpaceTimeAStar,
)


def signature(paths):
    return [tuple((p.x, p.y) for p in path.points) for path in paths]


def test_same_query_uses_bounded_memo_without_a_mutable_list_alias():
    memo = CandidateSearchCache(max_entries=2, max_points=30)
    planner = SpaceTimeAStar(3, 3, candidate_cache=memo)
    kwargs = {
        "start": Point(0, 0),
        "goal": Point(2, 2),
        "max_time_steps": 6,
        "max_expansions": 1000,
        "max_candidates": 2,
    }
    first = planner.find_bounded_candidate_paths(**kwargs)
    assert first[0].length == 4
    original = signature(first)
    first.clear()
    second = planner.find_bounded_candidate_paths(**kwargs)
    assert planner.last_candidate_cache_hit and signature(second) == original
    with pytest.raises(ValueError):
        second[0].points[0].x = 99
    for time in range(6):
        planner.find_bounded_candidate_paths(**dict(kwargs, start_time=time))
    assert len(memo.entries) <= 2 and memo.points <= 30
    planner.find_bounded_candidate_paths(**kwargs)
    assert not planner.last_candidate_cache_hit


@pytest.mark.parametrize(
    "changed",
    [
        "vertex",
        "edge",
        "permanent",
        "obstacle",
        "dimensions",
        "goal",
        "start",
        "start_time",
        "wait",
        "expansions",
        "horizon",
        "extra",
        "pool",
        "ignore_owner",
        "weights",
        "tie_break",
        "permanent_goal",
    ],
)
def test_every_search_semantic_change_invalidates_exact_memo(changed):
    memo = CandidateSearchCache()
    obstacles = set()
    reservations = ReservationTable()
    kwargs = {
        "start": Point(0, 0),
        "goal": Point(2, 0),
        "reservation_table": reservations,
        "start_time": 0,
        "max_time_steps": 5,
        "max_expansions": 1000,
        "max_candidates": 3,
    }
    cached = SpaceTimeAStar(3, 3, obstacles, candidate_cache=memo)
    cached.find_bounded_candidate_paths(**kwargs)
    cached.find_bounded_candidate_paths(**kwargs)
    assert cached.last_candidate_cache_hit
    if changed == "vertex":
        reservations.reserve_vertex("peer", Point(1, 0), 1)
    elif changed == "edge":
        reservations.reserve_edge("peer", Point(1, 0), Point(0, 0), 0)
    elif changed == "permanent":
        reservations._permanent_reservations[(2, 0)] = (0, "peer")
    elif changed == "obstacle":
        cached.obstacles.add(Point(1, 0))
    elif changed == "dimensions":
        cached.width = 4
    elif changed == "goal":
        kwargs["goal"] = Point(2, 1)
    elif changed == "start":
        kwargs["start"] = Point(0, 1)
    elif changed == "start_time":
        kwargs["start_time"] = 1
    elif changed == "wait":
        kwargs["allow_wait"] = False
    elif changed == "expansions":
        kwargs["max_expansions"] = 1
    elif changed == "horizon":
        kwargs["max_time_steps"] = 1
    elif changed == "extra":
        kwargs["max_extra_steps"] = 0
    elif changed == "pool":
        kwargs["max_candidates"] = 1
    elif changed == "ignore_owner":
        kwargs["ignore_agent_id"] = "peer"
    elif changed == "weights":
        kwargs["cell_weights"] = {Point(1, 0): 10.0}
    elif changed == "tie_break":
        kwargs["tie_break_weights"] = True
    elif changed == "permanent_goal":
        kwargs["permanent_at_goal"] = True
    actual = cached.find_bounded_candidate_paths(**kwargs)
    assert not cached.last_candidate_cache_hit, changed
    fresh = SpaceTimeAStar(cached.width, cached.height, cached.obstacles)
    assert signature(actual) == signature(fresh.find_bounded_candidate_paths(**kwargs))
    assert (cached.last_search_status, cached.last_expansions) == (
        fresh.last_search_status,
        fresh.last_expansions,
    )
    # A changed bounded failure must not reuse the earlier successful path.
    if changed in {"expansions", "horizon", "permanent"}:
        assert actual == []


def test_subclass_search_override_never_reuses_a_base_class_memo():
    memo = CandidateSearchCache()
    args = {"start": Point(0, 0), "goal": Point(2, 0)}
    SpaceTimeAStar(3, 3, candidate_cache=memo).find_bounded_candidate_paths(**args)

    class RefusingPlanner(SpaceTimeAStar):
        def search(self, *args, **kwargs):
            self.last_search_status = "plugin_refusal"

    custom = RefusingPlanner(3, 3, candidate_cache=memo)
    assert custom.find_bounded_candidate_paths(**args) == []
    assert (
        not custom.last_candidate_cache_hit
        and custom.last_search_status == "plugin_refusal"
    )


def test_custom_reservation_table_bypasses_memo_and_matches_uncached_search():
    class BlockingTable(ReservationTable):
        def is_vertex_reserved(self, p, t, ignore_agent_id=None):
            return t > 0

    memo = CandidateSearchCache()
    planner = SpaceTimeAStar(3, 3, candidate_cache=memo)
    kwargs = {"start": Point(0, 0), "goal": Point(2, 0), "max_time_steps": 4}
    assert planner.find_bounded_candidate_paths(
        **kwargs, reservation_table=ReservationTable()
    )
    actual = planner.find_bounded_candidate_paths(
        **kwargs, reservation_table=BlockingTable()
    )
    assert not planner.last_candidate_cache_hit
    expected = SpaceTimeAStar(3, 3).find_bounded_candidate_paths(
        **kwargs, reservation_table=BlockingTable()
    )
    assert signature(actual) == signature(expected)
