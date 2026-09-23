"""Storage corruption, retention and recovery must not manufacture a valid run."""

import hashlib
import json
import time
from copy import deepcopy

import pytest

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.jobs import completed_payload
from mapf.application.plans import preview, provenance
from mapf.application.runs import RunRepository, encode, new_id
from mapf.application.worker import solve_plan


@pytest.fixture(scope="module")
def payload():
    request = JobSubmissionRequest(grid_width=40, grid_height=2, starts={"a": (0, 0)},
        goals={"a": (39, 0)}, solver_id="CBS", setting="SETTING_4", max_steps=60)
    plan = preview(request)
    plan["provenance"] = provenance()
    job = {"job_id": new_id("job"), "run_id": new_id("run"), "attempt_id": new_id("attempt"),
           "definition_digest": plan["definition_digest"], "plan": plan,
           "effective_config": plan["effective_config"], "created_at": time.time(), "started_at": time.time()}
    return completed_payload(job, solve_plan(plan))


@pytest.fixture
def stored(tmp_path, payload):
    repository = RunRepository(tmp_path)
    repository.save_run(payload)
    return repository, payload["metadata"]["run_id"]


def replace_root(repository, run_id, change):
    path = repository.artifacts / f"{run_id}.json"
    root = json.loads(path.read_bytes())
    change(root)
    raw = encode(root)
    path.write_bytes(raw)
    checksum = hashlib.sha256(raw).hexdigest()
    with repository.connect() as database:
        database.execute("UPDATE runs SET sha256=? WHERE id=?", (checksum, run_id))
    return checksum


def test_missing_job_cannot_publish_an_unattached_result(tmp_path, payload):
    repository = RunRepository(tmp_path)
    with pytest.raises(KeyError):
        repository.save_run(payload, new_id("job"))
    assert repository.list_runs() == []
    assert list(repository.artifacts.iterdir()) == []


def test_immutable_run_rejection_preserves_input_and_existing_artifact(stored, payload):
    repository, run_id = stored
    original = deepcopy(payload)
    before = {path.name: path.read_bytes() for path in repository.artifacts.iterdir()}
    with pytest.raises(ValueError, match="immutable"):
        repository.save_run(payload)
    assert {path.name: path.read_bytes() for path in repository.artifacts.iterdir()} == before
    assert payload == original
    assert repository.get_run(run_id)["frames"] == payload["frames"]


@pytest.mark.parametrize(("offset", "limit"), [(-1, 1), (0, 0), (0, 101)])
def test_invalid_frame_slice_is_rejected(stored, offset, limit):
    repository, run_id = stored
    with pytest.raises(ValueError, match="Frame slice"):
        repository.frame_slice(run_id, offset, limit)


def test_slice_after_final_frame_is_empty_and_unknown_run_is_missing(stored):
    repository, run_id = stored
    assert repository.frame_slice(run_id, 500, 10)["frames"] == []
    with pytest.raises(KeyError):
        repository.frame_slice(new_id("run"), 0, 1)


@pytest.mark.parametrize(("field", "value", "message"), [
    ("file", "../outside.json.gz", "Malformed frame"),
    ("count", 99, "count mismatch"),
])
def test_checked_root_cannot_bypass_frame_reference_and_count_validation(stored, field, value, message):
    repository, run_id = stored
    replace_root(repository, run_id, lambda root: root["frames_index"][0].update({field: value}))
    with pytest.raises(ValueError, match=message):
        repository.frame_slice(run_id, 0, 2)


def test_progress_rejects_nonboolean_success_even_with_matching_checksum(stored):
    repository, run_id = stored
    checksum = replace_root(repository, run_id, lambda root: root["result"].update(success="true"))
    with pytest.raises(ValueError, match="must be boolean"):
        repository.verified_success(run_id, checksum)
    assert repository.verified_success(run_id, None) is None


def test_pin_protects_all_chunks_and_explicit_delete_removes_them(stored):
    repository, run_id = stored
    repository.pin(run_id, True)
    with pytest.raises(ValueError, match="Pinned"):
        repository.delete_run(run_id)
    assert repository.get_run(run_id)["frames"]
    repository.pin(run_id, False)
    repository.delete_run(run_id)
    assert repository.get_run(run_id) is None
    assert not list(repository.artifacts.glob(f"{run_id}*"))


def test_recovery_quarantines_orphan_chunks_but_keeps_committed_run(stored):
    repository, run_id = stored
    orphan_id = new_id("run")
    orphan = repository.artifacts / f"{orphan_id}.frames-000000.json.gz"
    orphan.write_bytes(b"unfinished chunk")
    attempt = repository.staging / f"{new_id('attempt')}.json"
    attempt.write_text("{}")
    assert repository.recover() == 0
    assert not orphan.exists() and not attempt.exists()
    assert (repository.staging / f"orphan-{orphan.name}").read_bytes() == b"unfinished chunk"
    assert repository.get_run(run_id)["frames"]


@pytest.mark.parametrize("corruption", ["malformed", "missing-column"])
def test_schema_inspection_fails_without_modifying_incompatible_database(tmp_path, corruption):
    repository = RunRepository(tmp_path)
    if corruption == "malformed":
        repository.db_path.write_bytes(b"not a database")
    else:
        with repository.connect() as database:
            database.execute("DROP TABLE batches")
    before = repository.db_path.read_bytes()
    with pytest.raises(ValueError, match="Invalid workspace|Incompatible workspace"):
        RunRepository.open_existing(tmp_path)
    assert repository.db_path.read_bytes() == before
