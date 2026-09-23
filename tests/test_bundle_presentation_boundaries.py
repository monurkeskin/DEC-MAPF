"""Public imports reject contradictory evidence; exports preserve safe values."""

import csv
import io
from copy import deepcopy

import pytest

from mapf.application.artifacts import (
    export_bundle,
    import_bundle,
    metrics_csv,
    svg_snapshot,
)
from mapf.application.runs import RunRepository
from tests.test_reduced_bundle import small_payload


@pytest.fixture(scope="module")
def recorded_run():
    return small_payload("full-trace")


@pytest.mark.parametrize(
    "fault", ["obstacle", "solver-outcome", "invalid-status", "reduced-frames"]
)
def test_recomputed_checksum_does_not_make_inconsistent_data_valid(
    tmp_path, recorded_run, fault
):
    payload = deepcopy(recorded_run)
    if fault == "obstacle":
        payload["metadata"]["instance"]["obstacles"].append(
            next(iter(payload["metadata"]["instance"]["starts"].values()))
        )
    elif fault == "solver-outcome":
        payload["result"]["solver_outcome"] = "failed"
    elif fault == "invalid-status":
        payload["result"].update(success=False, status="invalid")
    else:
        payload["metadata"]["effective_config"]["recording_level"] = "metrics-only"
    repo = RunRepository(tmp_path)
    with pytest.raises(ValueError):
        import_bundle(export_bundle(payload), repo)
    assert repo.list_runs() == []


@pytest.mark.parametrize("value", ["=1+1", "+SUM(A1)", "-2+3", "@formula"])
def test_csv_escapes_formula_prefix_without_rewriting_raw_metadata(recorded_run, value):
    payload = deepcopy(recorded_run)
    payload["metadata"]["solver_name"] = value
    row = next(csv.DictReader(io.StringIO(metrics_csv(payload))))
    assert row["solver_name"] == "'" + value
    assert payload["metadata"]["solver_name"] == value


def test_svg_keeps_goals_but_hides_disappeared_agents(recorded_run):
    payload = deepcopy(recorded_run)
    frame = payload["frames"][-1]
    for aid in frame["positions"]:
        frame["statuses"][aid] = "disappeared"
    svg = svg_snapshot(payload, len(payload["frames"]) - 1)
    assert "<circle" not in svg and " goal</title>" in svg
