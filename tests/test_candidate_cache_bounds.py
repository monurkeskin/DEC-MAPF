"""Eviction and replacement retain bounded receipts without changing paths."""

import pytest

from mapf.core.models import Path, Point
from mapf.core.space_time_grid import (
    CandidateSearchCache,
    ReservationTable,
    SpaceTimeAStar,
)


def path(length):
    return Path(points=[Point(i, 0) for i in range(length)])


@pytest.mark.parametrize("limits", [{"max_entries": 0}, {"max_points": 0}])
def test_cache_requires_positive_bounds(limits):
    with pytest.raises(ValueError, match="Positive"):
        CandidateSearchCache(**limits)


def test_replacement_updates_point_accounting_and_access_controls_eviction():
    cache = CandidateSearchCache(max_entries=2, max_points=5)
    cache.put(("a",), [path(2)], "found", 1)
    cache.put(("b",), [path(2)], "found", 2)
    assert cache.get(("a",)) == ((path(2),), "found", 1)
    cache.put(("c",), [path(3)], "found", 3)
    assert cache.get(("b",)) is None and cache.points == 5
    cache.put(("a",), [path(1)], "found", 4)
    assert cache.points == 4 and cache.get(("c",)) is not None
    cache.put(("a",), [path(6)], "found", 5)
    assert cache.points == 4 and cache.get(("a",)) == ((path(1),), "found", 4)


def test_reservation_clear_releases_vertices_reverse_edges_and_goal_parking():
    table = ReservationTable()
    table.reserve_path("empty", Path(points=[]), permanent=True)
    table.reserve_path("a", path(2), start_time=3, permanent=True)
    assert table.is_vertex_reserved(Point(1, 0), 100)
    assert not table.is_vertex_reserved(Point(1, 0), 100, ignore_agent_id="a")
    assert table.is_edge_conflict(Point(1, 0), Point(0, 0), 3)
    table.clear()
    assert not table.is_vertex_reserved(Point(1, 0), 100)
    assert not table.is_edge_conflict(Point(1, 0), Point(0, 0), 3)


def test_dynamic_reservation_override_bypasses_cached_candidate_results():
    cache = CandidateSearchCache()
    search = SpaceTimeAStar(3, 2, candidate_cache=cache)
    table = ReservationTable()
    assert search.find_bounded_candidate_paths(Point(0, 0), Point(2, 0), reservation_table=table)
    table.is_vertex_reserved = lambda p, t, ignore_agent_id=None: p == Point(2, 0)
    assert search.find_bounded_candidate_paths(Point(0, 0), Point(2, 0), reservation_table=table) == []
    assert not search.last_candidate_cache_hit


def test_custom_edge_queries_remain_active_with_no_stored_reservations():
    table = ReservationTable()
    table.is_edge_conflict = lambda u, v, t, ignore_agent_id=None: u == Point(0, 0) and v == Point(1, 0)
    result = SpaceTimeAStar(3, 2).search(Point(0, 0), Point(2, 0), reservation_table=table)
    assert result is not None and result.points[1] == Point(0, 1)


def test_custom_permanent_goal_requires_explicit_future_occupancy_contract():
    class ScheduledTable(ReservationTable):
        def is_vertex_reserved(self, point, tick, ignore_agent_id=None):
            return point == Point(2, 0) and tick == 3

    table = ScheduledTable()
    search = SpaceTimeAStar(3, 2)
    with pytest.raises(TypeError, match="can_park"):
        search.search(Point(0, 0), Point(2, 0), reservation_table=table, permanent_at_goal=True)
    table.can_park = lambda point, tick, ignored: tick > 3
    result = search.search(Point(0, 0), Point(2, 0), reservation_table=table, permanent_at_goal=True)
    assert result is not None and len(result.points) == 5
