"""Coordinate and path boundaries have explicit physical and value semantics."""

import pytest
from pydantic import ValidationError

from mapf.core.models import Path, Point


@pytest.mark.parametrize("allow_wait", [False, True], ids=["move-only", "wait-allowed"])
def test_neighbors_preserve_four_connected_motion_and_optional_wait(allow_wait):
    origin = Point(2, 3)
    expected = [Point(3, 3), Point(1, 3), Point(2, 4), Point(2, 2)]
    if allow_wait:
        expected.append(origin)
    assert origin.get_neighbors(allow_wait) == expected


def test_coordinates_are_immutable_values():
    origin = Point(2, 3)
    assert Point(x=2, y=3) == origin
    assert str(origin) == "(2,3)"
    with pytest.raises(ValidationError, match="frozen"):
        origin.x = 8


def test_manhattan_distance_counts_both_axes_across_zero():
    assert Point(2, 3).manhattan_distance(Point(-1, 7)) == 7


@pytest.mark.parametrize(
    ("tick", "disappear", "expected"),
    [
        (-1, False, None),
        (0, False, Point(0, 0)),
        (1, True, Point(1, 0)),
        (2, False, Point(1, 0)),
        (2, True, None),
    ],
    ids=["before-start", "initial", "arrival", "parked", "disappeared"],
)
def test_path_queries_distinguish_arrival_from_disappearance(tick, disappear, expected):
    path = Path([Point(0, 0), Point(1, 0)])
    assert path.at_time(tick, disappear) == expected


def test_remaining_paths_preserve_terminal_position_and_empty_trace():
    path = Path([Point(0, 0), Point(1, 0), Point(1, 1)])
    assert path.slice_from(1).points == (Point(1, 0), Point(1, 1))
    assert path.slice_from(3).points == (Point(1, 1),)
    assert path.slice_from(30).length == 0
    assert Path().slice_from(30).points == ()
    assert Path().at_time(0) is None
