"""OS process failures must close owned IPC and expose an unsuccessful stop."""

from unittest.mock import Mock

import pytest

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.deadlines import NegotiationWatch
from mapf.application.jobs import JobSupervisor
from mapf.application.resources import ResourcePolicy
from mapf.application.runs import RunRepository
from tests.test_supervisor_failures import BlockedProbe, terminal


@pytest.mark.parametrize("survives_kill", [False, True])
def test_cancellation_escalates_a_nonresponsive_owned_process(monkeypatch, survives_kill):
    group_stop = Mock()
    monkeypatch.setattr("mapf.application.jobs.stop_owned_group", group_stop)
    process = Mock(pid=12345)
    process.is_alive.side_effect = [True, True, survives_kill]
    channel = Mock()
    owned = (process, None, channel, NegotiationWatch())
    if survives_kill:
        with pytest.raises(RuntimeError, match="did not stop"):
            JobSupervisor._terminate(owned)
        process.close.assert_not_called()
    else:
        JobSupervisor._terminate(owned)
        process.close.assert_called_once()
        channel.close.assert_called_once()
    group_stop.assert_called_once_with(process.pid)
    process.terminate.assert_called_once()
    process.kill.assert_called_once()


def test_failed_process_start_closes_both_pipe_ends_and_records_failure(tmp_path):
    repo = RunRepository(tmp_path)
    owner = JobSupervisor(repo, resource_policy=ResourcePolicy(), resource_probe=BlockedProbe())
    receive, send = Mock(), Mock()
    process = Mock()
    process.start.side_effect = OSError("injected spawn resource failure")
    try:
        with owner._mutex:
            job = owner.submit(JobSubmissionRequest(scenario_id="crossing-2a"))
            owner._context = Mock()
            owner._context.Pipe.return_value = (receive, send)
            owner._context.Process.return_value = process
            owner.admission = None
        state = terminal(repo, job["job_id"])
        assert "spawn resource failure" in state["error"]
        assert repo.list_runs() == []
        assert owner._processes == {}
        receive.close.assert_called_once()
        send.close.assert_called_once()
        process.close.assert_called_once()
    finally:
        owner.close()


def test_monitor_stops_after_it_cannot_record_an_infrastructure_failure(tmp_path, monkeypatch):
    repo = RunRepository(tmp_path)
    owner = JobSupervisor(repo, resource_policy=ResourcePolicy(), resource_probe=BlockedProbe())
    try:
        with owner._mutex:
            owner.submit(JobSubmissionRequest(scenario_id="crossing-2a"))
            with monkeypatch.context() as patch:
                patch.setattr(repo, "transition", Mock(side_effect=OSError("unavailable journal")))
                owner._fail_active(OSError("original monitor failure"))
                assert owner._stop.is_set()
                assert "original monitor failure" in owner.last_error
        assert repo.list_runs() == []
    finally:
        owner.close()
