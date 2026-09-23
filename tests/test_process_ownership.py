"""A job owns native descendants even when its worker or supervisor dies."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.jobs import JobSupervisor
from mapf.application.runs import TERMINAL, RunRepository
from tests.worker_fixtures import native_child_worker


def wait_for(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.03)
    assert predicate(), "Owned native process did not reach the required state"


def running(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def clean_child(marker):
    if marker.exists():
        pid = int(marker.read_text())
        if running(pid):
            os.kill(pid, signal.SIGKILL)


@pytest.mark.parametrize("mode", ["cancel", "timeout", "worker_crash"])
def test_job_termination_stops_native_descendant(tmp_path, mode):
    repo = RunRepository(tmp_path)
    manager = JobSupervisor(repo, max_workers=1, worker=native_child_worker)
    marker = repo.staging / "native-child.pid"
    try:
        job = manager.submit(
            JobSubmissionRequest(
                scenario_id="crossing-2a",
                timeout_sec=3 if mode == "timeout" else 30,
                random_seed=99 if mode == "worker_crash" else 42,
            )
        )
        wait_for(marker.exists)
        pid = int(marker.read_text())
        if mode == "cancel":
            assert manager.cancel_job(job["job_id"])
        wait_for(lambda: repo.get_job(job["job_id"])["state"] in TERMINAL)
        wait_for(lambda: not running(pid), seconds=3)
        assert repo.list_runs() == []
    finally:
        manager.close()
        clean_child(marker)


def test_sigkill_of_supervisor_stops_worker_and_native_descendant(tmp_path):
    script = tmp_path / "owner.py"
    script.write_text("""from pathlib import Path
import sys,time
from mapf.application.runs import RunRepository
from mapf.application.jobs import JobSupervisor
from mapf.application.contracts import JobSubmissionRequest
from tests.worker_fixtures import native_child_worker
if __name__ == '__main__':
    root=Path(sys.argv[1])
    manager=JobSupervisor(RunRepository(root),max_workers=1,worker=native_child_worker)
    manager.submit(JobSubmissionRequest(scenario_id='crossing-2a',timeout_sec=50))
    time.sleep(60)
""")
    root = tmp_path / "runs"
    marker = root / "staging" / "native-child.pid"
    owner = subprocess.Popen(
        [sys.executable, str(script), str(root)],
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                (
                    str(Path(__file__).resolve().parents[1] / "src"),
                    str(Path(__file__).resolve().parents[1]),
                )
            ),
        },
    )
    try:
        wait_for(marker.exists)
        pid = int(marker.read_text())
        owner.kill()
        owner.wait(timeout=3)
        wait_for(lambda: not running(pid), seconds=4)
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=3)
        clean_child(marker)
