"""Workers report admission drift and bounded recording loss without starting work."""

import json
from types import SimpleNamespace

import pytest

from mapf.application import processes, worker
from mapf.telemetry.events import DiagnosticEvent


def test_recording_limit_counts_the_events_it_cannot_store():
    collector = worker.TraceCollector(limit=1)
    collector.capture(DiagnosticEvent("OBSERVATION", 0, {}))
    collector.capture(DiagnosticEvent("OBSERVATION", 1, {}))
    assert len(collector.events) == 1 and collector.dropped == 1
    assert collector.events[0]["sequence"] == 1


def test_source_drift_produces_a_failure_receipt_before_solving(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "provenance", lambda: {"source_sha256": "current"})
    solved = []
    monkeypatch.setattr(
        worker, "solve_plan", lambda *_args, **_kwargs: solved.append(True)
    )
    path = tmp_path / "receipt.json"
    worker.execute_worker(
        {"plan": {"provenance": {"source_sha256": "previous"}}}, str(path)
    )
    receipt = json.loads(path.read_text())
    assert not receipt["ok"] and "Source changed" in receipt["error"]
    assert solved == [] and "ValueError" in receipt["traceback"]


@pytest.mark.parametrize("disconnection", [EOFError, OSError])
def test_parent_loss_stops_only_the_owned_group(monkeypatch, disconnection):
    callbacks, stopped, exits = [], [], []
    monkeypatch.setattr(processes.os, "setsid", lambda: None)
    monkeypatch.setattr(processes.os, "getpid", lambda: 12345)
    monkeypatch.setattr(processes, "stop_owned_group", stopped.append)
    monkeypatch.setattr(processes.os, "_exit", exits.append)
    monkeypatch.setattr(
        processes.threading,
        "Thread",
        lambda *, target, daemon: SimpleNamespace(
            start=lambda: callbacks.append(target)
        ),
    )

    def disconnected():
        raise disconnection()

    started = []
    processes.run_owned_process(
        lambda *args: started.append(args),
        {},
        "out",
        SimpleNamespace(recv_bytes=disconnected),
    )
    assert len(started) == 1 and len(callbacks) == 1
    callbacks[0]()
    assert stopped == [12345] and exits == [70]
