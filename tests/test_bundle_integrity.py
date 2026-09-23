"""A recomputed checksum cannot legitimize contradictory scientific evidence."""

from copy import deepcopy

import pytest

from mapf.application.artifacts import export_bundle, import_bundle
from mapf.application.runs import RunRepository
from tests.test_reduced_bundle import small_payload


@pytest.fixture(scope="module")
def solved_payload():
    return small_payload("full-trace")


@pytest.mark.parametrize(("path", "value"), [
    (("result", "validation", "prefix_valid"), False),
    (("result", "validation", "first_violation_tick"), 1),
    (("result", "status"), "failed"),
    (("result", "solved_count"), 0),
    (("result", "total_agents"), 1),
    (("metadata", "solver_name"), "different-solver"),
    (("metadata", "run_id"), "run-" + "a" * 32),
], ids=["prefix", "violation", "status", "arrivals", "roster", "solver", "run"])
def test_checked_import_rejects_inconsistent_receipts(tmp_path, solved_payload, path, value):
    payload = deepcopy(solved_payload)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        import_bundle(export_bundle(payload), RunRepository(tmp_path))
    assert RunRepository(tmp_path).list_runs() == []


@pytest.mark.parametrize(("field", "value"), [
    ("active_agents", 0), ("solved_agents", 2), ("statuses", {}),
    ("positions", {}), ("phase", "post_move"), ("heat_grid", {"0-0": 999.0}),
], ids=["active", "solved", "lifecycle", "positions", "phase", "hindsight"])
def test_checked_import_rejects_forged_replay_even_when_both_copies_agree(
    tmp_path, solved_payload, field, value,
):
    payload = deepcopy(solved_payload)
    payload["frames"][0][field] = value
    payload["result"]["frames"][0][field] = value
    with pytest.raises(ValueError):
        import_bundle(export_bundle(payload), RunRepository(tmp_path))


def test_checked_import_rejects_a_false_validation_status(tmp_path, solved_payload):
    payload = deepcopy(solved_payload)
    payload["metadata"]["validation_status"] = "invalid"
    payload["result"]["validation"]["status"] = "invalid"
    with pytest.raises(ValueError):
        import_bundle(export_bundle(payload), RunRepository(tmp_path))


@pytest.mark.parametrize(("path", "value"), [
    (("metadata", "instance_hash"), "wrong"),
    (("metadata", "definition_digest"), "wrong"),
    (("metadata", "runtime_ms"), -1),
    (("metadata", "is_valid"), False),
    (("metadata", "validation_status"), "not_checked"),
    (("metadata", "effective_config", "setting"), "SETTING_4"),
    (("metadata", "instance", "setting"), "SETTING_4"),
    (("metadata", "effective_config", "recording_level"), "metrics-only"),
    (("metadata", "instance", "starts"), {}),
    (("result", "sum_of_costs"), 999),
    (("result", "validation"), None),
    (("result", "validation", "is_valid"), False),
], ids=["hash", "definition", "runtime", "validity", "validation-state", "effective-setting",
        "snapshot-setting", "recording", "scenario", "cost", "receipt", "receipt-validity"])
def test_existing_integrity_guards_reject_recomputed_checksums(tmp_path, solved_payload, path, value):
    payload = deepcopy(solved_payload)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        import_bundle(export_bundle(payload), RunRepository(tmp_path))


@pytest.mark.parametrize(("field", "value"), [("format", "unknown"), ("version", "9"),
                                               ("sha256", "wrong"), ("payload", [])])
def test_bad_envelopes_do_not_enter_the_repository(tmp_path, solved_payload, field, value):
    bundle = export_bundle(deepcopy(solved_payload))
    bundle[field] = value
    with pytest.raises(ValueError):
        import_bundle(bundle, RunRepository(tmp_path))


@pytest.mark.parametrize("missing", ["metadata", "result"])
def test_missing_payload_sections_are_reported_as_invalid_input(tmp_path, solved_payload, missing):
    payload = deepcopy(solved_payload)
    del payload[missing]
    with pytest.raises(ValueError):
        import_bundle(export_bundle(payload), RunRepository(tmp_path))


def test_two_frame_representations_must_agree(tmp_path, solved_payload):
    payload = deepcopy(solved_payload)
    payload["frames"] = []
    with pytest.raises(ValueError, match="representations disagree"):
        import_bundle(export_bundle(payload), RunRepository(tmp_path))


def test_checked_import_has_a_bounded_replay_size(tmp_path, solved_payload):
    payload = deepcopy(solved_payload)
    frames = [payload["frames"][0]] * 502
    payload["frames"] = frames
    payload["result"]["frames"] = frames
    payload["metadata"]["frame_count"] = 502
    with pytest.raises(ValueError, match="limits"):
        import_bundle(export_bundle(payload), RunRepository(tmp_path))
