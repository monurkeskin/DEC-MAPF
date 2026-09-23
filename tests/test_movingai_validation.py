"""Import and sampling contracts checked independently of the serializers."""
import pytest

from mapf.core.geometry import goal_distances
from mapf.core.models import Point
from mapf.core.movingai import (
    generate_benchmark_map,
    generate_stern_scenario,
    parse_movingai_map,
    parse_movingai_scen,
)


def test_map_terrain_symbols_and_header_order():
    width, height, obstacles = parse_movingai_map(
        "type octile\nwidth 7\nheight 1\nmap\n.GS@TOW\n"
    )
    assert (width, height) == (7, 1)
    assert obstacles == {Point(x, 0) for x in range(3, 7)}


@pytest.mark.parametrize("content", [
    "", "type cardinal\nheight 1\nwidth 1\nmap\n.",
    "type octile\nheight 1\nwidth\nmap\n.",
    "type octile\nheight\nwidth 1\nmap\n.",
    "type octile\nheight 1\nwidth bad\nmap\n.",
    "type octile\nheight 0\nwidth 1\nmap\n.",
    "type octile\nheight 2\nwidth 1\nmap\n.",
    "type octile\nheight 1\nwidth 2\nmap\n.",
    "type octile\nheight 1\nwidth 1\nmap\n?",
], ids=["empty", "wrong-type", "missing-width", "missing-height", "nonnumeric",
        "zero-height", "missing-row", "short-row", "unknown-terrain"])
def test_malformed_maps_raise_value_error(content):
    with pytest.raises(ValueError):
        parse_movingai_map(content)


@pytest.mark.parametrize("content", ["", "version 2", "version 1\n0 map 3 3"],
                         ids=["empty", "wrong-version", "missing-columns"])
def test_malformed_scenario_structure_is_rejected(content):
    with pytest.raises(ValueError):
        parse_movingai_scen(content)


@pytest.mark.parametrize("column,value", [
    (2, "0"), (3, "0"), (4, "-1"), (4, "3"), (5, "3"), (6, "-1"),
    (7, "3"), (4, "invalid"), (8, "-1"), (8, "nan"), (8, "inf"),
], ids=["zero-width", "zero-height", "negative-start", "start-x-outside",
        "start-y-outside", "negative-goal", "goal-y-outside", "nonnumeric",
        "negative-distance", "nan-distance", "infinite-distance"])
def test_scenario_coordinates_and_distance_must_be_valid(column, value):
    row = ["0", "fixture.map", "3", "3", "0", "0", "2", "2", "4"]
    row[column] = value
    with pytest.raises(ValueError, match="Malformed MovingAI scenario row"):
        parse_movingai_scen("version 1\n" + "\t".join(row))


def test_scenario_comments_and_blank_lines_preserve_row_order():
    data = "version 1\n# comment\n\n0 map 3 3 0 0 2 2 4\n0 map 3 3 1 0 1 2 2\n"
    assert parse_movingai_scen(data) == [(Point(0, 0), Point(2, 2)),
                                           (Point(1, 0), Point(1, 2))]


@pytest.mark.parametrize("width,height,density", [(0, 3, 0), (3, 0, 0), (3, 3, -0.1),
                                                 (3, 3, 1), (3, 3, float("nan"))],
                         ids=["width", "height", "negative", "full", "nan"])
def test_synthetic_maps_reject_invalid_dimensions_and_density(width, height, density):
    with pytest.raises(ValueError):
        generate_benchmark_map(width, height, density)


def test_synthetic_sampling_does_not_cross_disconnected_components():
    wall = {Point(2, y) for y in range(4)}
    pairs = generate_stern_scenario(5, 4, wall, 12, min_dist=1, max_dist=3, seed=19)
    assert len({start for start, _ in pairs}) == 12
    assert len({goal for _, goal in pairs}) == 12
    for start, goal in pairs:
        assert (start.x < 2) == (goal.x < 2)
        assert 1 <= start.manhattan_distance(goal) <= 3


@pytest.mark.parametrize("kwargs,reason", [
    ({"num_agents": 0}, "Invalid synthetic"),
    ({"min_dist": 3, "max_dist": 1}, "Invalid synthetic"),
    ({"num_agents": 10}, "Not enough traversable"),
    ({"min_dist": 10, "max_dist": 10, "max_attempts": 5}, "Only 0 pairs"),
    ({"max_attempts": 0}, "Only 0 pairs"),
], ids=["no-agents", "reversed-bounds", "too-many-agents", "impossible-distance", "no-attempts"])
def test_synthetic_sampling_never_relaxes_requested_constraints(kwargs, reason):
    parameters = {"width": 3, "height": 3, "obstacles": set(), "num_agents": 1,
                  "min_dist": 1, "max_dist": 3, **kwargs}
    with pytest.raises(ValueError, match=reason):
        generate_stern_scenario(**parameters)


def test_blocked_or_outside_goal_has_no_static_distances():
    assert not goal_distances(2, 2, frozenset({(1, 1)}), (1, 1))
    assert not goal_distances(2, 2, frozenset(), (2, 2))
