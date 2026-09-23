"""Absolute-time and reverse-edge commitment witnesses independent of planning."""

import pytest

from mapf.core.commitments import CommitmentReservation
from mapf.core.models import Path, Point
from mapf.core.space_time_grid import ReservationTable


def route(*cells):
    return Path(points=[Point(*p) for p in cells])


def promise(policy="SC"):
    return CommitmentReservation(
        "agreement", "a", "b", 5, (Point(0, 0), Point(1, 0), Point(2, 0)), policy
    )


@pytest.mark.parametrize(
    ("policy", "tick", "cell", "active"),
    [
        ("ZC", 6, Point(1, 0), False),
        ("DC", 7, Point(2, 0), True),
        ("DC", 8, Point(2, 0), False),
        ("SC", 7, Point(2, 0), True),
        ("SC", 8, Point(2, 0), False),
    ],
    ids=[
        "zero-released",
        "dynamic-last-tick",
        "dynamic-released",
        "standard-last-tick",
        "standard-released",
    ],
)
def test_commitment_blocks_through_its_last_active_tick(policy, tick, cell, active):
    reservation = promise(policy)
    table = ReservationTable()
    reservation.add_to(table, tick)
    assert table.is_vertex_reserved(cell, tick) is active
    assert reservation.conflicts_with(Path([cell]), tick, stay_at_goal=True) is active


def test_reverse_edge_conflict_needs_both_endpoints_in_the_same_tick():
    reservation = promise()
    assert reservation.conflicts_with(route((1, 0), (0, 0)), 5, stay_at_goal=False)
    assert not reservation.conflicts_with(route((1, 0), (1, 1)), 5, stay_at_goal=False)
    assert not reservation.conflicts_with(route((0, 0), (0, 1)), 6, stay_at_goal=False)


def test_goal_occupancy_distinguishes_stay_from_disappear():
    reservation = promise()
    path = route((2, 0))
    assert reservation.conflicts_with(path, 5, stay_at_goal=True)
    assert not reservation.conflicts_with(path, 5, stay_at_goal=False)
    table = ReservationTable()
    reservation.add_to(table, 6)
    assert not table.is_vertex_reserved(Point(0, 0), 5)
    assert table.is_vertex_reserved(Point(1, 0), 6)
    assert table.is_edge_conflict(Point(2, 0), Point(1, 0), 6)
