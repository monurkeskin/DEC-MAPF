import json
import time

import pytest

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.jobs import completed_payload
from mapf.application.plans import preview, provenance
from mapf.application.runs import RunRepository, new_id
from mapf.application.worker import solve_plan


def test_real_long_path_chunk_seek_integrity_and_export_materialization(tmp_path):
    plan = preview(JobSubmissionRequest(grid_width=40, grid_height=2, starts={"a": (0, 0)},
                                       goals={"a": (39, 0)}, solver_id="CBS", max_steps=60, setting="SETTING_4"))
    plan["provenance"] = provenance()
    job = {"job_id": new_id("job"), "run_id": new_id("run"), "attempt_id": new_id("attempt"),
           "definition_digest": plan["definition_digest"], "plan": plan, "effective_config": plan["effective_config"],
           "created_at": time.time(), "started_at": time.time()}
    payload = completed_payload(job, solve_plan(plan))
    repository = RunRepository(tmp_path)
    repository.save_run(payload)
    rid = job["run_id"]
    root = json.loads((repository.artifacts / f"{rid}.json").read_text())
    assert len(root["frames_index"]) == 2
    assert root["frames"] == root["result"]["frames"] == []
    assert repository.frame_slice(rid, 31, 3)["frames"] == payload["frames"][31:34]
    assert repository.get_run(rid)["frames"] == payload["frames"]
    chunk = repository.artifacts / root["frames_index"][1]["file"]
    chunk.write_bytes(b"tampered")
    assert len(repository.frame_slice(rid, 0, 2)["frames"]) == 2
    with pytest.raises(ValueError, match="integrity"):
        repository.frame_slice(rid, 32, 2)
