"""Hand-calculated cohorts include every planned failure and missing result."""

from copy import deepcopy

import pytest

from mapf.analytics.experiment import analyze_experiment


def rows():
    values = []
    for instance, left, right in [("a", 10, 12), ("b", 20, "timed_out"),
                                  ("c", "invalid", 8), ("d", "not_admitted", "not_admitted")]:
        for solver, outcome in (("L", left), ("R", right)):
            solved = isinstance(outcome, int)
            values.append({"trial_id": f"{instance}-{solver}", "instance_hash": instance, "sampling_unit": instance,
                               "solver_id": solver, "setting": "SETTING_4", "fov_size": 5, "commitment_type": "SC",
                               "random_seed": 1, "source_sha256": "fixed", "metric_version": "v2",
                               "state": "completed" if solved or outcome == "invalid" else outcome,
                               "validation_status": "valid_solution" if solved else "invalid" if outcome == "invalid" else "not_checked",
                               "success": solved, "sum_of_costs": outcome if solved else None, "runtime_ms": 10 if solved else None})
    return values


def test_all_planned_denominators_and_common_solved_costs():
    result = analyze_experiment(rows(), "L", "R")
    assert result["left"]["planned"] == result["right"]["planned"] == 4
    assert result["left"]["success_rate"] == result["right"]["success_rate"] == 0.5
    assert result["coverage"] == {"both_solved": 1, "left_only": 1, "right_only": 1, "neither": 1, "unpaired": 0}
    assert result["cost"]["mean_delta_right_minus_left"] == 2
    assert result["cost"]["interval"] is None  # one independent unit cannot establish precision
    assert result["left"]["outcomes"]["invalid"] == 1
    assert result["right"]["outcomes"]["timed_out"] == 1
    assert result["success_difference"]["estimate_right_minus_left"] == 0


def test_pairing_permutation_duplicate_and_configuration_mismatch():
    data = rows()
    assert analyze_experiment(list(reversed(data)), "L", "R") == analyze_experiment(data, "L", "R")
    with pytest.raises(ValueError, match="Duplicate"):
        analyze_experiment(data + [deepcopy(data[0])], "L", "R")
    data[1]["fov_size"] = 7
    assert analyze_experiment(data, "L", "R")["coverage"]["unpaired"] == 2
