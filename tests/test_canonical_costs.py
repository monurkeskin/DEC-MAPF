from mapf.core.models import Path, Point
from mapf.metrics.costs import trajectory_costs
from mapf.solvers.base import MAPFInstance


def test_goal_padding_is_not_action_cost_and_obstacle_baseline_is_not_manhattan():
    inst = MAPFInstance(
        grid_width=3,
        grid_height=2,
        starts={"a": Point(0, 0)},
        goals={"a": Point(2, 0)},
        obstacles={Point(1, 0)},
    )
    p = Path(
        points=[
            Point(0, 0),
            Point(0, 1),
            Point(1, 1),
            Point(2, 1),
            Point(2, 0),
            Point(2, 0),
        ]
    )
    costs = trajectory_costs(inst, {"a": p})
    assert costs["action_sum_of_costs"] == 4
    assert costs["recorded_action_count"] == 5
    assert costs["independent_shortest_path_sum"] == 4
    assert costs["individual_detour_ratio"] == 0
    assert costs["paper_eq2"] is None


def test_stationary_single_move_and_incomplete_costs():
    inst = MAPFInstance(
        grid_width=2, grid_height=1, starts={"a": Point(0, 0)}, goals={"a": Point(1, 0)}
    )
    assert (
        trajectory_costs(inst, {"a": Path(points=[Point(0, 0), Point(1, 0)])})[
            "action_sum_of_costs"
        ]
        == 1
    )
    assert (
        trajectory_costs(inst, {"a": Path(points=[Point(0, 0)])})["action_sum_of_costs"]
        is None
    )
    inst = inst.model_copy(update={"goals": {"a": Point(0, 0)}})
    assert (
        trajectory_costs(inst, {"a": Path(points=[Point(0, 0)])})["action_sum_of_costs"]
        == 0
    )
