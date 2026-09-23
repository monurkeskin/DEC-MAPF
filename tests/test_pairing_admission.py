"""Hand-counted cohort witnesses prevent retry selection and false pairing."""

from copy import deepcopy

import pytest

from mapf.application.comparison import compare_runs


class MetadataRepository:
    def __init__(self, *metadata):
        self.records = {m["run_id"]: {"metadata": m} for m in metadata}

    def get_run(self, run_id, *, include_frames):
        assert not include_frames
        return deepcopy(self.records.get(run_id))


def record(run_id, instance="one", solver="CBS", *, success=True, valid=True):
    return {"run_id": run_id, "instance_hash": instance, "success": success, "is_valid": valid,
            "effective_config": {"solver_id": solver, "random_seed": 7, "agent_order": ["a", "b"]},
            "provenance": {"source_sha256": "same-source"}, "metric_version": "same-metric",
            "sum_of_costs": 10, "makespan": 6, "runtime_ms": 2}


@pytest.mark.parametrize(("left", "right", "keys", "message"), [
    (["a"], ["a"], ["solver_id"], "both comparison"),
    (["a"], ["b"], [], "at least one"),
    (["a"], ["b"], ["random_seed"], "Treatment keys"),
    (["a", "retry"], ["b"], ["solver_id"], "Repeated attempt"),
])
def test_ambiguous_selection_is_rejected(left, right, keys, message):
    repository = MetadataRepository(record("a"), record("retry"), record("b", solver="Prioritized"))
    with pytest.raises(ValueError, match=message):
        compare_runs(repository, left, right, keys)


def test_missing_run_is_not_silently_dropped():
    with pytest.raises(KeyError, match="missing"):
        compare_runs(MetadataRepository(record("a")), ["a"], ["missing"], ["solver_id"])


@pytest.mark.parametrize("difference", ["source", "metric", "seed", "order"])
def test_identity_difference_cannot_be_paired_as_a_solver_treatment(difference):
    left, right = record("a"), record("b", solver="Prioritized")
    if difference == "source":
        right["provenance"]["source_sha256"] = "changed-source"
    elif difference == "metric":
        right["metric_version"] = "changed-metric"
    elif difference == "seed":
        right["effective_config"]["random_seed"] = 8
    else:
        right["effective_config"]["agent_order"] = ["b", "a"]
    result = compare_runs(MetadataRepository(left, right), ["a"], ["b"], ["solver_id"])
    assert result["paired"] == 0 and result["unmatched"] == {"left": 1, "right": 1}
    assert result["means_right_minus_left"]["sum_of_costs"] is None


def test_invalid_successes_and_failed_trials_stay_in_denominator():
    left = [record("a1", "one"), record("a2", "two"), record("a3", "three", success=False),
            record("a4", "four", valid=False), record("unmatched", "five")]
    right = [record("b1", "one", "Prioritized"), record("b2", "two", "Prioritized", valid=False),
             record("b3", "three", "Prioritized"), record("b4", "four", "Prioritized", success=False)]
    right[0].update(sum_of_costs=14, makespan=7, runtime_ms=5)
    result = compare_runs(MetadataRepository(*left, *right), [r["run_id"] for r in left],
                          [r["run_id"] for r in right], ["solver_id"])
    assert result["attempted"] == {"left": 5, "right": 4}
    assert result["paired"] == 4 and result["excluded_from_costs"] == 3
    assert result["paired_coverage"] == {"both_solved": 1, "left_only": 1, "right_only": 1, "neither_solved": 1}
    assert result["means_right_minus_left"] == {"sum_of_costs": 4, "makespan": 1, "runtime_ms": 3}
    excluded = [row for row in result["rows"] if not row["common_solved"]]
    assert all(set(row["deltas_right_minus_left"].values()) == {None} for row in excluded)
