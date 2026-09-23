"""Independent values for the legacy disclosure proxy and batch denominator."""

import pytest

from mapf.core.models import Path, Point
from mapf.metrics.evaluator import (
    calculate_information_sharing_rate,
    evaluate_batch_results,
)


def test_proposals_count_only_explicit_points_on_the_senders_trajectory():
    paths = {"a": [Point(0, 0), Point(1, 0)], "b": [Point(4, 0), Point(5, 0)]}
    history = [
        {
            "agent_a": "a",
            "agent_b": "b",
            "shared_points_a": [Point(0, 0), Point(9, 9)],
            "shared_points_b": paths["b"],
        },
        {"agent_a": "a", "shared_points_a": paths["a"]},
        {"agent_a": "a", "agent_b": "b"},
    ]
    assert (
        calculate_information_sharing_rate(paths, [], negotiation_history=history)
        == 0.75
    )


def test_repeated_visits_are_spatially_deduplicated_and_empty_agents_remain_peers():
    paths = {"a": [Point(0, 0), Point(0, 0), Point(1, 0)], "b": [], "c": []}
    history = [{"agent_a": "a", "agent_b": "b", "shared_points_a": [Point(0, 0)]}]
    # Half of a's distinct spatial cells disclosed to one of its two peers.
    assert (
        calculate_information_sharing_rate(paths, [], negotiation_history=history)
        == 0.25
    )


@pytest.mark.parametrize(
    "paths",
    [{}, {"a": [Point(0, 0)]}, {"a": [], "b": []}],
    ids=["no-agents", "single-agent", "empty-trajectories"],
)
def test_no_pairwise_disclosure_population_has_zero_legacy_proxy(paths):
    assert calculate_information_sharing_rate(paths, []) == 0.0


def test_broadcast_proxy_handles_absent_empty_and_short_recipient_paths():
    paths = {"a": [Point(0, 0), Point(1, 0)], "b": [Point(0, 1)]}
    history = [{"a": Path([])}, {"a": Path(paths["a"])}]
    assert calculate_information_sharing_rate(paths, history) == 0.0
    history = [{"a": Path(paths["a"])}]
    assert calculate_information_sharing_rate(paths, history, fov_size=3) == 0.5


def test_batch_retains_failed_trials_and_matches_only_positive_optimal_references():
    runs = [
        {
            "scenario_id": "known",
            "success": True,
            "total_steps": 6,
            "negotiation_count": 2,
            "total_path_length": 12,
        },
        {
            "scenario_id": "zero",
            "success": True,
            "total_steps": 0,
            "total_path_length": 0,
        },
        {"scenario_id": "unknown", "success": True, "total_steps": 3},
        {
            "scenario_id": "failed",
            "success": False,
            "total_steps": 100,
            "negotiation_count": 10,
        },
        {"scenario_id": "defaults", "success": True},
        {"scenario_id": "missing-success"},
    ]
    assert evaluate_batch_results(runs, {"known": 8, "zero": 0, "failed": 1}) == {
        "total_runs": 6,
        "solved_runs": 4,
        "solution_rate": 0.6667,
        "average_makespan": 2.25,
        "average_negotiations": 2.0,
        "average_optimality_gap": 0.5,
    }


def test_empty_and_unsolved_batches_do_not_invent_an_optimality_reference():
    assert evaluate_batch_results([]) == {"solution_rate": 0.0, "total_runs": 0}
    summary = evaluate_batch_results([{"success": False}], {"missing": 2})
    assert summary["total_runs"] == 1 and summary["solved_runs"] == 0
    assert summary["solution_rate"] == 0.0
    assert (
        summary["average_makespan"] == 0.0
    )  # Existing legacy empty-aggregate convention.
    assert summary["average_optimality_gap"] is None
