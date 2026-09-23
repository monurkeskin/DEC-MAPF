"""OS probe failures remain unknown measurements, never fabricated free capacity."""

import sys
from types import SimpleNamespace

import pytest

from mapf.application.resources import (
    MIB,
    ResourceAdmission,
    ResourcePolicy,
    ResourceSnapshot,
    SystemResourceProbe,
    resource_kind,
)


class ProcessError(Exception):
    pass


class MissingProcess(ProcessError):
    pass


class Process:
    def __init__(self, rss, children=(), failure=None):
        self.rss, self.descendants, self.failure = rss, children, failure

    def children(self, *, recursive):
        assert recursive
        return self.descendants

    def memory_info(self):
        if self.failure:
            raise self.failure("process changed while sampling")
        return SimpleNamespace(rss=self.rss)


def install_probe(monkeypatch, processes, *, failure=None):
    def lookup(pid):
        if failure:
            raise failure("cannot inspect process")
        if pid not in processes:
            raise MissingProcess("already exited")
        return processes[pid]

    def cpu(*, interval):
        assert interval == 0.05
        return 12.5

    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(
        Error=ProcessError, NoSuchProcess=MissingProcess, Process=lookup,
        virtual_memory=lambda: SimpleNamespace(available=4096 * MIB), cpu_percent=cpu))
    return SystemResourceProbe()


def test_probe_sums_owned_tree_and_tolerates_processes_exiting_between_reads(monkeypatch):
    parent = Process(30, [Process(20), Process(99, failure=MissingProcess)])
    probe = install_probe(monkeypatch, {12: parent})
    snapshot = probe.sample({"live": 12, "gone": 13})
    assert snapshot.available_bytes == 4096 * MIB
    assert snapshot.cpu_percent == 12.5
    assert snapshot.rss_bytes == {"live": 50, "gone": 0}
    assert snapshot.error is None


@pytest.mark.parametrize("failure", [ProcessError, PermissionError])
def test_inaccessible_process_tree_does_not_become_zero_usage(monkeypatch, failure):
    probe = install_probe(monkeypatch, {}, failure=failure)
    snapshot = probe.sample({"active": 12})
    assert snapshot.available_bytes is None and snapshot.cpu_percent is None
    assert snapshot.rss_bytes == {}
    assert type(failure()).__name__ in snapshot.error
    admission = ResourceAdmission(ResourcePolicy(), probe)
    pending = [{"job_id": "new", "effective_config": {"solver_id": "HeatMap", "suboptimality": 1}}]
    assert admission.choose(pending, [], {"active": 12}, 1, now=0) == []
    assert admission.latest["blocked"] == {"new": "resource_telemetry_unavailable"}


def test_resources_extra_is_required_only_when_constructing_system_probe(monkeypatch):
    monkeypatch.setitem(sys.modules, "psutil", None)
    with pytest.raises(ValueError, match="resources extra"):
        SystemResourceProbe()


@pytest.mark.parametrize(("family", "weight", "expected"), [
    ("eecbs", 1.0, "optimal"), ("eecbs", 1.2, "bounded"), ("cbsh2-rtc", 1.0, "optimal")])
def test_native_family_and_weight_determine_memory_reservation(family, weight, expected):
    job = {"effective_config": {"solver_id": "configured-native", "native_profile": {"family": family},
                                "suboptimality": weight}}
    assert resource_kind(job) == expected


@pytest.mark.parametrize("snapshot", [ResourceSnapshot(None, 10), ResourceSnapshot(4 * MIB, None)],
                         ids=["missing-memory", "missing-cpu"])
def test_partial_telemetry_is_not_sufficient_for_admission(snapshot):
    class Probe:
        def sample(self, processes):
            return snapshot
    admission = ResourceAdmission(ResourcePolicy(), Probe())
    jobs = [{"job_id": "new", "effective_config": {"solver_id": "HeatMap", "suboptimality": 1}}]
    assert admission.choose(jobs, [], {}, 1, now=0) == []
    assert admission.latest["blocked"]["new"] == "resource_telemetry_unavailable"


def test_snapshot_cache_expires_and_blocked_idle_period_resets():
    class Probe:
        calls = 0
        def sample(self, processes):
            self.calls += 1
            return ResourceSnapshot(64 * 1024 * MIB, 99 if self.calls == 1 else 0)
    probe = Probe()
    admission = ResourceAdmission(ResourcePolicy(), probe)
    jobs = [{"job_id": "new", "effective_config": {"solver_id": "HeatMap", "suboptimality": 1}}]
    assert admission.choose(jobs, [], {}, 1, now=10) == []
    assert admission.blocked_since == 10
    assert admission.choose(jobs, [], {}, 1, now=10.5) == []
    assert probe.calls == 1 and admission.blocked_since == 10
    assert admission.choose(jobs, [], {}, 1, now=11) == jobs
    assert probe.calls == 2 and admission.blocked_since is None
