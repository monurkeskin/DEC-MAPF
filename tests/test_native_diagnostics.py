"""Real pipe drainage and recovery of the last snapshot after hard termination."""

import json
import sys
import time

import pytest

from mapf.application.native_diagnostics import (
    diagnostic_path,
    read_diagnostics,
    write_diagnostics,
)
from mapf.solvers._native_io import NativeFiles
from mapf.solvers._native_process import run_native


def snapshot_then_block(job, output, connection):
    write_diagnostics(
        output, job, {"statistics": {"HL expanded": "427"}, "stdout": "searching"}
    )
    time.sleep(30)


def test_supervisor_preserves_native_snapshot_on_hard_process_deadline(tmp_path):
    from mapf.application.contracts import JobSubmissionRequest
    from mapf.application.jobs import JobSupervisor
    from mapf.application.runs import RunRepository

    repo = RunRepository(tmp_path)
    owner = JobSupervisor(repo, worker=snapshot_then_block)
    try:
        job = owner.submit(
            JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=1)
        )
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            finished = repo.get_job(job["job_id"])
            if finished["state"] == "timed_out":
                break
            time.sleep(0.02)
        assert finished["state"] == "timed_out"
        assert finished["timeout_scope"] == "process"
        assert finished["timeout_diagnostics"]["statistics"] == {"HL expanded": "427"}
        assert repo.list_runs() == []
        assert not diagnostic_path(repo.staging / f"{job['attempt_id']}.json").exists()
    finally:
        owner.close()


def test_process_timeout_drains_both_streams_with_bounded_memory():
    snapshots = []
    code = "import os, time; os.write(1, b'x' * 100000); os.write(2, b'y' * 100000 + b'\\xff'); time.sleep(10)"
    result = run_native([sys.executable, "-c", code], 0.8, snapshots.append)
    assert result.timed_out and result.returncode != 0
    assert result.stdout == "x" * 4000
    assert result.stderr == "y" * 3999 + "\ufffd"
    assert snapshots[-1]["stdout_bytes"] == 100000
    assert snapshots[-1]["stderr_bytes"] == 100001
    assert snapshots[-1]["stdout_truncated"] and snapshots[-1]["stderr_truncated"]
    assert snapshots[0]["exit_code"] is None


def test_snapshot_failure_reaps_the_child():
    pids = []

    def fail(snapshot):
        pids.append(snapshot["pid"])
        raise OSError("storage unavailable")

    with pytest.raises(OSError, match="storage unavailable"):
        run_native([sys.executable, "-c", "import time; time.sleep(10)"], 1, fail)
    import os

    with pytest.raises(ProcessLookupError):
        os.kill(pids[0], 0)


def test_partial_statistics_preserve_only_the_last_complete_record(tmp_path):
    files = NativeFiles(tmp_path)
    files.statistics.write_text("solution cost,HL expanded\n-1,427\n12,")
    assert files.read_statistics() == {"solution cost": "-1", "HL expanded": "427"}
    files.statistics.write_bytes(b"x" * 65537)
    assert "64 KiB" in files.read_statistics()["_diagnostic"]


def test_native_snapshot_is_bound_to_the_attempt_and_recovers_after_output_loss(
    tmp_path,
):
    job = {"job_id": "j", "attempt_id": "a", "run_id": "r"}
    output = tmp_path / "a.json"
    details = {"stdout": "searching", "statistics": {"HL expanded": "427"}}
    write_diagnostics(output, job, details)
    assert not output.exists()
    assert read_diagnostics(output, job)["statistics"] == {"HL expanded": "427"}
    assert (
        "identity mismatch"
        in read_diagnostics(output, {**job, "attempt_id": "other"})["unavailable"]
    )
    diagnostic_path(output).write_text(json.dumps({**job, "diagnostics": []}))
    assert "must be an object" in read_diagnostics(output, job)["unavailable"]
    diagnostic_path(output).write_bytes(b"x" * (512 * 1024 + 1))
    assert "exceeds 512 KiB" in read_diagnostics(output, job)["unavailable"]


@pytest.mark.parametrize(
    "arguments",
    [
        ("--lowLevelSolver=false", "--highLevelSolver=A*"),
        ("--highLevelSolver", "A*", "--lowLevelSolver", "0"),
    ],
)
def test_cbs_low_level_allows_astar_declaration(tmp_path, arguments):
    from mapf.solvers.binary_runner import ExternalBinarySolver

    solver = ExternalBinarySolver(
        tmp_path / "fixture", setting_arguments={"SETTING_4": arguments}
    )
    assert solver.setting_arguments["SETTING_4"] == arguments
