from __future__ import annotations

from mapf.core.models import Path, Point
from mapf.core.movingai import (
    export_planviz_json,
    export_standard_paths,
    format_movingai_map,
    format_movingai_scen,
    parse_movingai_map,
    parse_movingai_scen,
)


def test_movingai_map_roundtrip() -> None:
    obstacles = {Point(x=1, y=1), Point(x=2, y=2)}
    map_str = format_movingai_map(width=4, height=4, obstacles=obstacles)
    w, h, parsed_obs = parse_movingai_map(map_str)
    assert w == 4
    assert h == 4
    assert parsed_obs == obstacles


def test_movingai_scen_roundtrip() -> None:
    pairs = [
        (Point(x=0, y=0), Point(x=3, y=3)),
        (Point(x=1, y=2), Point(x=2, y=1)),
    ]
    scen_str = format_movingai_scen(pairs, map_name="test.map", width=4, height=4)
    parsed_pairs = parse_movingai_scen(scen_str)
    assert len(parsed_pairs) == 2
    assert parsed_pairs[0] == (Point(x=0, y=0), Point(x=3, y=3))
    assert parsed_pairs[1] == (Point(x=1, y=2), Point(x=2, y=1))


def test_export_standard_paths_and_planviz() -> None:
    paths = {
        "agent_0": Path(points=[Point(x=0, y=0), Point(x=0, y=1), Point(x=1, y=1)]),
        "agent_1": Path(points=[Point(x=3, y=3), Point(x=2, y=3), Point(x=1, y=3)]),
    }
    std_out = export_standard_paths(paths)
    assert "agent_0: (0,0)->(0,1)->(1,1)" in std_out
    assert "agent_1: (3,3)->(2,3)->(1,3)" in std_out

    planviz_json = export_planviz_json(paths, map_name="empty-4-4.map", width=4, height=4)
    assert planviz_json["teamSize"] == 2
    assert len(planviz_json["actualPaths"]) == 2
    assert "0,0,0,0,F" in planviz_json["actualPaths"][0]
