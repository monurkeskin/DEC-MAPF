from hypothesis import given
from hypothesis import strategies as st

from mapf.core.models import Path, Point
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar


def test_basic_path_finding_no_obstacles():
    planner = SpaceTimeAStar(grid_width=10, grid_height=10)
    start = Point(x=0, y=0)
    goal = Point(x=5, y=5)

    path = planner.search(start, goal)
    assert path is not None
    assert path.points[0] == start
    assert path.points[-1] == goal
    # Optimal Manhattan distance is 10 action steps (11 points total)
    assert path.length == 10
    assert len(path.points) == 11


def test_path_finding_with_obstacle():
    obstacles = {Point(x=1, y=0), Point(x=1, y=1)}
    planner = SpaceTimeAStar(grid_width=5, grid_height=5, obstacles=obstacles)
    start = Point(x=0, y=0)
    goal = Point(x=2, y=0)

    path = planner.search(start, goal)
    assert path is not None
    assert path.points[0] == start
    assert path.points[-1] == goal
    for pt in path.points:
        assert pt not in obstacles


def test_space_time_vertex_conflict_avoidance():
    planner = SpaceTimeAStar(grid_width=10, grid_height=10)
    res_table = ReservationTable()

    # Another agent has reserved (1, 0) at t=1
    path_a = Path(points=[Point(x=1, y=1), Point(x=1, y=0), Point(x=1, y=0)])
    res_table.reserve_path(agent_id="Agent_A", path=path_a, start_time=0)

    start = Point(x=0, y=0)
    goal = Point(x=2, y=0)

    path_b = planner.search(start, goal, start_time=0, reservation_table=res_table)
    assert path_b is not None
    # Verify Agent B did not enter (1, 0) at t=1
    assert path_b.at_time(1) != Point(x=1, y=0)


def test_edge_swap_conflict_avoidance():
    """Agent A moves (0,0) -> (1,0) at t=0->1. Agent B starting at (1,0) cannot move to (0,0) at t=0->1."""
    planner = SpaceTimeAStar(grid_width=5, grid_height=5)
    res_table = ReservationTable()

    # Agent A moves from (0,0) to (1,0) at t=0
    path_a = Path(points=[Point(x=0, y=0), Point(x=1, y=0)])
    res_table.reserve_path(agent_id="Agent_A", path=path_a, start_time=0)

    # Agent B wants to go from (1,0) to (0,0)
    start_b = Point(x=1, y=0)
    goal_b = Point(x=0, y=0)

    path_b = planner.search(
        start_b, goal_b, start_time=0, reservation_table=res_table, allow_wait=True
    )
    assert path_b is not None
    # Ensure Agent B waited or detoured rather than swapping head-on
    assert not (
        path_b.points[0] == Point(x=1, y=0) and path_b.points[1] == Point(x=0, y=0)
    )


@given(
    gx=st.integers(min_value=1, max_value=8),
    gy=st.integers(min_value=1, max_value=8),
)
def test_hypothesis_path_invariant(gx: int, gy: int):
    """Property-based invariant: for any destination on an empty grid, distance is optimal."""
    planner = SpaceTimeAStar(grid_width=10, grid_height=10)
    start = Point(x=0, y=0)
    goal = Point(x=gx, y=gy)

    path = planner.search(start, goal)
    assert path is not None
    # Calculate expected distances without the Point helper used by the planner.
    assert path.points[0] == start and path.points[-1] == goal
    assert path.length == gx + gy
    # Check consecutive points are valid 1-step moves
    for i in range(len(path.points) - 1):
        before, after = path.points[i], path.points[i + 1]
        d = abs(before.x - after.x) + abs(before.y - after.y)
        assert d in (0, 1)


def test_space_time_permanent_reservation():
    """Agent parked at goal at t=1 blocks that cell for all t >= 1."""
    planner = SpaceTimeAStar(grid_width=5, grid_height=5)
    res_table = ReservationTable()
    parked_path = Path(points=[Point(x=2, y=2)])
    res_table.reserve_path(
        agent_id="Agent_Parked", path=parked_path, start_time=1, permanent=True
    )

    # Agent B starts at t=0 at (0, 2) and reaches (2, 2) at t=2 >= 1
    path_b = planner.search(
        Point(x=0, y=2), Point(x=2, y=2), start_time=0, reservation_table=res_table
    )
    # Target is permanently blocked, cannot end at (2,2)
    assert path_b is None


def test_space_time_cell_weights():
    """Heavy cell weight causes planner to detour around weighted cells."""
    planner = SpaceTimeAStar(grid_width=5, grid_height=5)
    start = Point(x=0, y=0)
    goal = Point(x=2, y=0)

    # Place heavy congestion penalty on direct cell (1, 0)
    cell_weights = {Point(x=1, y=0): 50.0}
    path = planner.search(start, goal, cell_weights=cell_weights)

    assert path is not None
    # Must detour through y=1 rather than paying 50.0 penalty at (1, 0)
    assert Point(x=1, y=0) not in path.points


def test_space_time_max_expansions_bound():
    """Completely trapped agent hits expansion bound and returns None cleanly."""
    # Box agent in with obstacles
    obstacles = {Point(x=1, y=0), Point(x=0, y=1)}
    planner = SpaceTimeAStar(grid_width=5, grid_height=5, obstacles=obstacles)
    path = planner.search(Point(x=0, y=0), Point(x=4, y=4), max_expansions=10)
    assert path is None
    assert planner.last_search_status == "expansion_limit"


def test_find_bounded_candidate_paths():
    """Verify bounded candidate paths adhere to L_min + 1 bound and are conflict-free."""
    planner = SpaceTimeAStar(grid_width=8, grid_height=8)
    start = Point(x=0, y=0)
    goal = Point(x=4, y=4)

    candidates = planner.find_bounded_candidate_paths(
        start=start,
        goal=goal,
        start_time=0,
        max_extra_steps=1,
        max_candidates=6,
    )

    assert len(candidates) >= 2
    l_min = len(candidates[0].points) - 1
    assert l_min == 8  # Manhattan distance 4 + 4

    for cand in candidates:
        assert cand.points[0] == start
        assert cand.points[-1] == goal
        cand_len = len(cand.points) - 1
        assert cand_len in (l_min, l_min + 1)


def test_precomputed_static_distance_table():
    """Precomputed static distance table provides valid distances and guides search around obstacles."""
    from mapf.core.space_time_grid import compute_static_distance_table

    # A maze wall blocking direct path: wall at x=2 from y=0 to y=3
    obstacles = {Point(x=2, y=y) for y in range(4)}
    goal = Point(x=4, y=0)
    dist_table = compute_static_distance_table(
        width=6,
        height=6,
        obstacles=obstacles,
        goal=goal,
    )

    # (0, 0) cannot go straight through wall at x=2, must navigate around (y >= 4)
    # Manhattan distance to (4,0) is 4; the shortest obstacle-free route is:
    # (0,0)->(1,0)->(1,1)->(1,2)->(1,3)->(1,4)->(2,4)->(3,4)->(3,3)->(3,2)->(3,1)->(3,0)->(4,0) -> 12 steps
    dist_start = dist_table[(0, 0)]
    assert dist_start == 12

    planner = SpaceTimeAStar(grid_width=6, grid_height=6, obstacles=obstacles)
    path = planner.search(
        start=Point(x=0, y=0),
        goal=goal,
        heuristic_table=dist_table,
    )
    assert path is not None
    assert path.points[0] == Point(x=0, y=0)
    assert path.points[-1] == goal
    assert path.length == 12
    # Assert path does not touch obstacles
    for pt in path.points:
        assert pt not in obstacles
