"""Spawn targets for process-lifecycle tests, without importing test modules.

Keep imports local when only a particular worker needs application services.
Spawn unpickles these targets in a fresh interpreter; importing HTTP clients or
pytest there adds startup cost unrelated to the behavior under test.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def uncooperative_worker(job, output, connection):
    time.sleep(60)


def crash_worker(job, output, connection):
    os._exit(19)


def failed_worker(job, output, connection):
    Path(output).write_text(
        json.dumps({"ok": False, "error": "injected solver adapter failure"})
    )


def stale_source_worker(job, output, connection):
    Path(output).write_text(
        json.dumps({"ok": False, "error": "Source changed before worker execution"})
    )


def blocked_owned_worker(job, output, connection):
    from mapf.application import worker

    def blocked_plan(plan, **kwargs):
        # Publish readiness from inside execution, after the watchdog is running.
        marker = Path(output).parent / "solver-entered.pid"
        temporary = marker.with_suffix(".tmp")
        temporary.write_text(str(os.getpid()))
        temporary.replace(marker)
        time.sleep(60)

    worker.solve_plan = blocked_plan
    worker.owned_worker(job, output, connection)


def supervisor_that_can_crash(directory):
    from mapf.application.contracts import JobSubmissionRequest
    from mapf.application.jobs import JobSupervisor
    from mapf.application.runs import RunRepository

    repo = RunRepository(directory)
    manager = JobSupervisor(repo, worker=blocked_owned_worker)
    job = manager.submit(
        JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=30)
    )
    while repo.get_job(job["job_id"])["state"] != "running":
        time.sleep(0.02)
    marker = Path(directory, "owned-process.json")
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(repo.get_job(job["job_id"])))
    temporary.replace(marker)
    time.sleep(60)


def native_child_worker(job, output, connection):
    marker = Path(output).parent / "native-child.pid"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import os,signal,time,pathlib,sys; "
                "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.tmp'); "
                "q.write_text(str(os.getpid())); q.replace(p); time.sleep(60)"
            ),
            str(marker),
        ]
    )
    if job["effective_config"]["random_seed"] == 99:
        while not marker.exists():
            time.sleep(0.01)
        os._exit(19)
    child.wait()


def cpu_heavy_worker(job, output, connection):
    # Spend CPU in the owned child independently of a solver's speed.
    marker = Path(output).with_suffix(".busy")
    marker.write_text(str(os.getpid()))
    deadline = time.monotonic() + 20
    value = 1
    while time.monotonic() < deadline:
        value = (value * 1103515245 + 12345) % 2147483647
