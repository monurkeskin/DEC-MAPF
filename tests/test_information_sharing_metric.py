from __future__ import annotations

from mapf.core.models import Path, Point
from mapf.metrics.evaluator import calculate_information_sharing_rate


def test_is_rate_disjoint_agents():
    """Two agents on opposite sides of grid with disjoint paths share 0% information."""
    # Agent 1 moves along y=0 from x=0 to 3
    # Agent 2 moves along y=15 from x=0 to 3 (distance = 15 > FoV radius 2)
    sol_paths = {
        "A1": [Point(x=0, y=0), Point(x=1, y=0), Point(x=2, y=0), Point(x=3, y=0)],
        "A2": [Point(x=0, y=15), Point(x=1, y=15), Point(x=2, y=15), Point(x=3, y=15)],
    }
    broadcasts = [
        {"A1": Path(points=sol_paths["A1"]), "A2": Path(points=sol_paths["A2"])}
        for _ in range(4)
    ]

    is_rate = calculate_information_sharing_rate(sol_paths, broadcasts, fov_size=5)
    assert is_rate == 0.0


def test_is_rate_interacting_agents_bounded():
    """Two agents crossing each other in close proximity share bounded information."""
    sol_paths = {
        "A1": [Point(x=1, y=1), Point(x=2, y=1), Point(x=3, y=1), Point(x=4, y=1)],
        "A2": [Point(x=4, y=1), Point(x=3, y=1), Point(x=2, y=1), Point(x=1, y=1)],
    }
    broadcasts = [
        {"A1": Path(points=sol_paths["A1"]), "A2": Path(points=sol_paths["A2"])}
        for _ in range(4)
    ]

    is_rate_path_aware = calculate_information_sharing_rate(
        sol_paths, broadcasts, fov_size=5, is_heatmap=False
    )
    is_rate_heatmap = calculate_information_sharing_rate(
        sol_paths, broadcasts, fov_size=5, is_heatmap=True
    )

    # Both must be strictly between 0 and 1.0
    assert 0.0 < is_rate_heatmap <= is_rate_path_aware <= 1.0
