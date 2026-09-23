"""Interoperable input syntax must not change source order or provenance."""

import pytest

from mapf.core.models import Point
from mapf.core.movingai import parse_movingai_map, parse_movingai_scen


@pytest.mark.parametrize("version", ["1", "1.0"])
def test_standard_scenario_versions_preserve_order(version):
    content = f"version {version}\n0 a.map 3 2 2 0 0 1 2.41421356\n1 a.map 3 2 0 0 2 1 2.41421356\n"
    assert parse_movingai_scen(content) == [
        (Point(2, 0), Point(0, 1)),
        (Point(0, 0), Point(2, 1)),
    ]


@pytest.mark.parametrize(
    "header",
    [
        "height 1\nwidthjunk 1\nmap",
        "height 1\nwidth 1 extra\nmap",
        "height 1\nwidth 2\nwidth 1\nmap",
        "height 1\nwidth 1\nmap extra",
        "height 1\nwidth 1\nunknown 1\nmap",
    ],
)
def test_ambiguous_map_headers_are_rejected(header):
    with pytest.raises(ValueError):
        parse_movingai_map(f"type octile\n{header}\n.\n")


@pytest.mark.parametrize("row", ["version 1", "version 2", "version garbage"])
def test_embedded_version_lines_are_not_silently_discarded(row):
    with pytest.raises(ValueError):
        parse_movingai_scen(f"version 1\n0 a.map 2 2 0 0 1 1 2\n{row}\n")


@pytest.mark.parametrize(
    "content,reason",
    [
        ("type octile\nheight 2\nmap\n..\n..\n", "width and height before map"),
        ("type octile\nheight 1\nwidth 1\n", "map body marker"),
    ],
    ids=["missing-dimension", "missing-body-marker"],
)
def test_incomplete_map_headers_identify_the_missing_structure(content, reason):
    with pytest.raises(ValueError, match=reason):
        parse_movingai_map(content)


@pytest.mark.parametrize("dimensions", [(0, 2), (2, 0)])
def test_archive_bounds_override_cannot_hide_invalid_declared_dimensions(dimensions):
    from mapf.core.movingai import parse_movingai_rows

    width, height = dimensions
    content = f"version 1\n0 a.map {width} {height} 0 0 1 1 2\n"
    with pytest.raises(ValueError, match="Malformed MovingAI scenario row"):
        parse_movingai_rows(content, coordinate_bounds=(2, 2))


def test_coordinate_export_retains_empty_trajectories_without_fabricated_moves():
    from mapf.core.models import Path
    from mapf.core.movingai import export_planviz_json

    paths = {"b": Path(points=[Point(2, 1)]), "a": Path(points=[])}
    exported = export_planviz_json(paths, "example.map", 3, 2)
    assert exported["actualPaths"] == ["", "2,1,0,0,F"]
    assert len(exported["start"]) == len(exported["actualPaths"]) == 2
    assert exported["start"][1] == [2, 1, 0]
    assert paths["a"].points == ()
