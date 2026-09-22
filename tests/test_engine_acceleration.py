from __future__ import annotations

from mapf.core.models import Path, Point
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar


def test_zero_allocation_reservation_table() -> None:
    res = ReservationTable()
    p1 = Point(x=2, y=2)
    p2 = Point(x=2, y=3)
    p3 = Point(x=2, y=4)

    path = Path(points=[p1, p2, p3])
    res.reserve_path("agent_0", path, start_time=0, permanent=True)

    # Vertex reservations
    assert res.is_vertex_reserved(p1, 0)
    assert res.is_vertex_reserved(p2, 1)
    assert res.is_vertex_reserved(p3, 2)
    assert res.is_vertex_reserved(p3, 10)  # Permanent reservation
    assert not res.is_vertex_reserved(p1, 1)

    # Edge reservations
    assert res.is_edge_conflict(p2, p1, 0)  # Agent traversed p1 -> p2 at t=0, so opposing p2 -> p1 at t=0 is conflict
    assert not res.is_edge_conflict(p1, p2, 0)

    # Ignore agent
    assert not res.is_vertex_reserved(p1, 0, ignore_agent_id="agent_0")
    assert not res.is_edge_conflict(p2, p1, 0, ignore_agent_id="agent_0")


def test_space_time_astar_with_primitive_reservations() -> None:
    planner = SpaceTimeAStar(grid_width=5, grid_height=5)
    res = ReservationTable()

    # Place an obstacle agent crossing the corridor
    cross_path = Path(points=[Point(x=2, y=0), Point(x=2, y=1), Point(x=2, y=2)])
    res.reserve_path("agent_cross", cross_path, start_time=1)

    # Plan path from (0, 1) to (4, 1)
    p = planner.search(
        start=Point(x=0, y=1),
        goal=Point(x=4, y=1),
        start_time=0,
        reservation_table=res,
        allow_wait=True,
    )

    assert p is not None
    assert p.points[0] == Point(x=0, y=1)
    assert p.points[-1] == Point(x=4, y=1)

    # Verify that planned path has no vertex collision with cross_path
    for t, pt in enumerate(p.points):
        assert not res.is_vertex_reserved(pt, t, ignore_agent_id="me")
