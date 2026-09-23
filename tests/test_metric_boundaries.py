"""Hand-calculated cost and disclosure cases preserve undefined scientific values."""

import pytest

from mapf.core.models import Path, Point
from mapf.metrics.costs import certified_optimality_gap, trajectory_costs
from mapf.metrics.evaluator import (
    calculate_information_sharing_rate,
)
from mapf.solvers.base import MAPFInstance


@pytest.mark.parametrize("paths", [{}, {"a": Path(points=[Point(0, 0)])}])
def test_unreachable_goal_does_not_create_a_finite_lower_bound(paths):
    instance = MAPFInstance(
        grid_width=3,
        grid_height=2,
        obstacles={Point(1, 0), Point(1, 1)},
        starts={"a": Point(0, 0)},
        goals={"a": Point(2, 0)},
    )
    metrics = trajectory_costs(instance, paths)
    assert metrics["arrival_ticks"] == {"a": None}
    assert metrics["independent_shortest_path_sum"] is None
    assert metrics["action_sum_of_costs"] is None
    assert metrics["individual_detour_ratio"] is None


@pytest.mark.parametrize(
    ("cost", "reference", "same", "optimal", "expected"),
    [
        (5, 4, True, True, 0.25),
        (0, 0, True, True, 0.0),
        (3, 0, True, True, None),
        (5, 4, False, True, None),
        (5, 4, True, False, None),
        (5, -1, True, True, None),
    ],
    ids=[
        "matched-optimal",
        "stationary",
        "positive-cost-zero-reference",
        "different-instance",
        "uncertified-reference",
        "negative-reference",
    ],
)
def test_certified_gap_requires_matched_optimal_reference(
    cost, reference, same, optimal, expected
):
    assert (
        certified_optimality_gap(
            cost, reference, identical_instance=same, reference_is_optimal=optimal
        )
        == expected
    )


def test_cost_below_certified_optimum_is_an_explicit_contradiction():
    with pytest.raises(ValueError, match="below the claimed optimal"):
        certified_optimality_gap(
            3, 4, identical_instance=True, reference_is_optimal=True
        )


def test_legacy_disclosure_counts_unique_spatial_points_and_explicit_shared_proposals():
    a, b = [Point(x, 0) for x in range(3)], [Point(x, 1) for x in range(3)]
    paths = {"a": [*a, a[-1]], "b": b}
    broadcast = [{"a": Path(points=a), "b": Path(points=[])}]
    assert calculate_information_sharing_rate(paths, broadcast, fov_size=3) == 0.5
    proposals = [
        {"agent_a": "a", "agent_b": "b", "shared_points_b": [b[0], b[0]]},
        {"shared_points_a": a},
        {"agent_a": "a", "agent_b": "b"},
    ]
    assert calculate_information_sharing_rate(
        paths, broadcast, fov_size=3, negotiation_history=proposals
    ) == pytest.approx(2 / 3)


def test_broadcast_outside_recipient_field_of_view_discloses_nothing():
    paths = {"a": [Point(0, 0)], "b": [Point(9, 9)]}
    assert (
        calculate_information_sharing_rate(
            paths, [{"a": Path(points=paths["a"])}], fov_size=3
        )
        == 0
    )
