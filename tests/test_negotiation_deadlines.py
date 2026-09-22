"""Article deadline scope, using hand-timed sessions and real owned workers."""
import time
from types import SimpleNamespace

import pytest

from mapf.agents.greedy import GreedyAgent
from mapf.application.contracts import JobSubmissionRequest
from mapf.application.deadlines import NegotiationWatch
from mapf.application.experiments import compile_experiment
from mapf.application.jobs import JobSupervisor
from mapf.application.plans import preview
from mapf.application.runs import RunRepository
from mapf.application.worker import owned_worker
from mapf.core.models import Point, SimulationConfig
from mapf.engine.world import WorldSimulation
from mapf.negotiation.conflict import detect_conflicts
from mapf.negotiation.session import BilateralNegotiationSession


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def parties(monkeypatch, clock, bid_seconds=31, accept=False):
    env = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2))
    a = GreedyAgent("a", Point(0, 0), Point(2, 0), 100)
    b = GreedyAgent("b", Point(2, 0), Point(0, 0), 100)
    for agent in (a, b):
        env.add_agent(agent)
        agent.plan_initial_path(env)
        original = agent.make_bid

        def bid(*args, _original=original, **kwargs):
            clock.now += bid_seconds
            return _original(*args, **kwargs)

        monkeypatch.setattr(agent, "make_bid", bid)
        monkeypatch.setattr(agent, "propose_response", lambda *args, _agent=agent:
            SimpleNamespace(accepted=accept, proposed_path=_agent.planned_path, components={}))
    conflict = detect_conflicts({"a": a.planned_path, "b": b.planned_path})[0]
    return a, b, conflict, env


def test_new_session_resets_clock_but_each_offer_does_not(monkeypatch):
    clock, events = Clock(), []
    session = BilateralNegotiationSession(max_rounds=100, protocol="taop-v1",
        deadline_sec=60, clock=clock, lifecycle_hook=events.append)
    args = parties(monkeypatch, clock)
    assert session.negotiate(*args, 0) is None
    assert clock.now == 62
    assert session.last_session_rounds == 2
    assert session.last_session_reason == "NEGOTIATION_DEADLINE"
    # Same world tick, a new bilateral session; cumulative elapsed already >600s.
    clock.now = 700
    assert session.negotiate(*args, 0) is None
    assert clock.now == 762
    assert [e["deadline"] for e in events if e["type"] == "negotiation_started"] == [60, 760]
    assert len({e["session_id"] for e in events}) == 2


def test_late_bid_cannot_change_tokens_plans_or_commitments(monkeypatch):
    clock = Clock()
    a, b, conflict, env = parties(monkeypatch, clock, bid_seconds=60, accept=True)
    original = (a.planned_path, b.planned_path)
    session = BilateralNegotiationSession(protocol="taop-v1", deadline_sec=60, clock=clock)
    assert session.negotiate(a, b, conflict, env, 0) is None
    assert session.last_session_reason == "NEGOTIATION_DEADLINE"
    assert (a.planned_path, b.planned_path) == original
    assert (a.tokens, b.tokens) == (100, 100)
    assert not a._commitments and not b._commitments


def test_preparation_is_inside_the_negotiation_budget(monkeypatch):
    clock = Clock()
    args = parties(monkeypatch, clock, bid_seconds=0)
    monkeypatch.setattr(args[0], "on_pre_negotiation", lambda *args: setattr(clock, "now", 61))
    session = BilateralNegotiationSession(protocol="taop-v1", deadline_sec=60, clock=clock)
    assert session.negotiate(*args, 0) is None
    assert session.last_session_rounds == 0
    assert session.last_session_reason == "NEGOTIATION_DEADLINE"


def test_deadline_stops_scenario_before_any_movement(monkeypatch):
    env = WorldSimulation(SimulationConfig(grid_width=3, grid_height=2))
    env.add_agent(GreedyAgent("a", Point(0, 0), Point(2, 0), 5))
    env.add_agent(GreedyAgent("b", Point(2, 0), Point(0, 0), 5))

    def expired(*args, **kwargs):
        env.negotiator.last_session_reason = "NEGOTIATION_DEADLINE"

    monkeypatch.setattr(env.negotiator, "negotiate", expired)
    result = env.run()
    assert result["termination_reason"] == "negotiation_deadline"
    assert result["total_steps"] == 0
    assert all(len(path) == 1 for path in result["path_history"].values())
    assert not result["success"]


def test_deadline_watch_does_not_renew_or_clear_a_different_session():
    watch = NegotiationWatch()
    watch.receive({"type": "negotiation_started", "session_id": "a", "deadline": 60})
    assert not watch.expired(59.99)
    assert watch.expired(60)
    for event in [
        {"type": "negotiation_started", "session_id": "a", "deadline": 120},
        {"type": "negotiation_finished", "session_id": "old"},
    ]:
        with pytest.raises(ValueError):
            watch.receive(event)
        assert watch.expired(60)
    watch.receive({"type": "negotiation_finished", "session_id": "a"})
    assert not watch.expired(700)
    watch.receive({"type": "negotiation_started", "session_id": "b", "deadline": 760})
    assert not watch.expired(700)


@pytest.mark.parametrize("deadline", [None, float("nan"), float("inf"), "60"])
def test_malformed_watch_deadline_is_rejected(deadline):
    with pytest.raises(ValueError):
        NegotiationWatch().receive({"type": "negotiation_started", "session_id": "a", "deadline": deadline})


def test_optional_overall_cap_is_distinct_from_negotiation_deadline():
    request = JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=None, negotiation_deadline_sec=60)
    plan = preview(request)
    assert plan["effective_config"]["timeout_sec"] is None
    assert plan["effective_config"]["negotiation_deadline_sec"] == 60
    manifest = compile_experiment({"name": "article deadline", "scenarios": [request.model_dump(mode="json")],
        "budget": {"workers": 1, "wall_seconds": 30, "max_trials": 1, "disk_mb": 64}})
    assert manifest["maximum_process_seconds"] is None
    assert manifest["budget"]["wall_seconds"] == 30
    with pytest.raises(ValueError, match="centralized"):
        preview(request.model_copy(update={"solver_id": "CBS"}))


def stuck_negotiation(job, output, connection):
    started = time.monotonic()
    connection.send({"type": "negotiation_started", "session_id": "stuck", "tick": 0,
        "deadline": started + job["effective_config"]["negotiation_deadline_sec"]})
    connection.send({"type": "negotiation_progress", "session_id": "stuck",
        "diagnostics": {"phase": "response", "agent": "a", "round": 7,
                        "acknowledged_usage": {"a": 3, "b": 2}, "observed_monotonic": started}})
    while True:
        time.sleep(1)


def multiple_short_negotiations(job, output, connection):
    deadline_sec = job["effective_config"]["negotiation_deadline_sec"]
    started = time.monotonic()
    for i in range(6):
        connection.send({"type": "negotiation_started", "session_id": str(i), "tick": i,
            "deadline": time.monotonic() + deadline_sec})
        time.sleep(deadline_sec / 5)
        connection.send({"type": "negotiation_finished", "session_id": str(i)})
    # The combined sessions exceed one deadline; no individual session should.
    assert time.monotonic() - started > deadline_sec
    owned_worker(job, output, connection)


@pytest.mark.parametrize("worker,expected,deadline_sec", [
    (stuck_negotiation, "timed_out", 0.2),
    # Leave scheduler headroom on shared CI runners. Exact boundary/reset
    # semantics are covered above with an injected clock, without wall sleeps.
    (multiple_short_negotiations, "completed", 2.0),
])
def test_hard_deadline_supervision_is_per_session(tmp_path, worker, expected, deadline_sec):
    repository = RunRepository(tmp_path)
    supervisor = JobSupervisor(repository, max_workers=1, worker=worker)
    try:
        job = supervisor.submit(JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=None,
            negotiation_deadline_sec=deadline_sec))
        end = time.monotonic() + 15
        while time.monotonic() < end:
            current = repository.get_job(job["job_id"])
            if current["state"] not in {"pending", "running"}:
                break
            time.sleep(0.02)
        assert current["state"] == expected, current
        if expected == "timed_out":
            assert current["timeout_scope"] == "negotiation"
            assert current["timeout_session_id"] == "stuck"
            detail = current["timeout_diagnostics"]
            assert detail["phase"] == "response" and detail["round"] == 7
            assert detail["acknowledged_usage"] == {"a": 3, "b": 2}
            assert detail["seconds_since_progress"] >= .2
    finally:
        supervisor.close()
