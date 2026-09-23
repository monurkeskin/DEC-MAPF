"""Independent analysis oracles for empty, clustered and incomplete populations."""

from copy import deepcopy

import pytest

from mapf.analytics.experiment import analyze_experiment, export_analysis


def trial(instance, solver, cost, **extra):
    return {"trial_id": f"{instance}-{solver}", "instance_hash": instance,
            "solver_id": solver, "source_sha256": "fixed", "metric_version": "v2",
            "state": "completed", "validation_status": "valid_solution", "success": True,
            "sum_of_costs": cost, "runtime_ms": 3, **extra}


def test_empty_population_has_no_estimate_or_interval():
    result = analyze_experiment([], "L", "R")
    assert result["pairs"] == result["included_trial_ids"] == []
    assert result["left"]["planned"] == result["right"]["planned"] == 0
    assert result["left"]["success_rate"] is None
    assert result["cost"]["mean_delta_right_minus_left"] is None
    assert result["success_difference"]["interval"] is None


def test_cluster_weights_do_not_treat_repeated_treatments_as_independent_scenarios():
    data = [trial("a1", "L", 4, sampling_unit="a"), trial("a2", "L", 4, sampling_unit="a"),
            trial("b", "L", None, sampling_unit="b", success=False)]
    result = analyze_experiment(data, "L", "R")
    assert result["left"]["success_rate"] == pytest.approx(2 / 3)
    assert result["left"]["scenario_weighted_success_rate"] == 0.5
    assert result["left"]["independent_units"] == 2
    assert result["left"]["outcomes"] == {"solved": 2, "not_solved": 1}
    assert result["coverage"]["unpaired"] == 3


def test_pair_costs_use_common_solved_only_and_zero_reference_is_undefined():
    data = [trial("a", "L", 0), trial("a", "R", 2), trial("b", "L", 4), trial("b", "R", 2)]
    result = analyze_experiment(data, "L", "R")
    assert result["cost"]["mean_delta_right_minus_left"] == 0
    assert result["cost"]["independent_units"] == 2
    pairs = {pair["left_trial"]: pair for pair in result["pairs"]}
    assert pairs["a-L"]["paper_eq2_left"] is None
    assert pairs["a-L"]["paper_eq2_right"] is None
    assert pairs["b-L"]["paper_eq2_left"] == 1
    assert pairs["b-L"]["paper_eq2_right"] == 0


def test_analysis_filters_do_not_mutate_the_raw_trial_table():
    data = [trial("a", "L", 4, fov_size=5), trial("a", "R", 6, fov_size=5),
            trial("b", "L", 3, fov_size=7), trial("a", "X", 2, fov_size=5)]
    original = deepcopy(data)
    result = analyze_experiment(data, "L", "R", filters={"fov_size": [5]})
    assert result["included_trial_ids"] == ["a-L", "a-R"]
    assert data == original
    assert result["cost"]["mean_delta_right_minus_left"] == 2
    assert result["cost"]["interval"] is None


@pytest.mark.parametrize("failure", ["same-solver", "duplicate-attempt", "sampling-unit"])
def test_invalid_pairing_fails_before_returning_estimates(failure):
    data = [trial("a", "L", 4), trial("a", "R", 5)]
    right = "R"
    if failure == "same-solver":
        right = "L"
    if failure == "duplicate-attempt":
        data.append({**data[0], "trial_id": "retry"})
    if failure == "sampling-unit":
        data[1]["sampling_unit"] = "another-unit"
    with pytest.raises(ValueError):
        analyze_experiment(data, "L", right)


@pytest.mark.parametrize("populated", [False, True], ids=["empty", "paired"])
def test_exports_keep_denominators_escape_labels_and_hash_every_artifact(tmp_path, populated):
    import csv
    import hashlib
    import json

    label = "L_&%$#{}~^\\"
    data = [trial("a", label, 4), trial("a", "R", 5),
            trial("b", label, 4), trial("b", "R", 6)] if populated else []
    result = analyze_experiment(data, label, "R")
    receipt = export_analysis(result, tmp_path)
    assert json.loads((tmp_path / "analysis.json").read_text()) == result
    with (tmp_path / "paired-table.csv").open() as stream:
        assert len(list(csv.DictReader(stream))) == (2 if populated else 0)
    latex = (tmp_path / "summary.tex").read_text()
    assert r"L\_\&\%\$\#\{\}\textasciitilde{}\textasciicircum{}\textbackslash{}" in latex
    assert ("100.00" if populated else "NA") in latex
    for name, digest in receipt["files"].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest
    assert {"success.svg", "success.pdf", "success.png"} <= receipt["files"].keys()
