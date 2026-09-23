"""Recorded fields must be actual strategy inputs, not retrospective trajectories."""

import pytest

from mapf.agents.heatmap import HeatMapAgent
from mapf.application.contracts import FrameSnapshot, JobSubmissionRequest
from mapf.application.plans import preview
from mapf.application.worker import TraceCollector, solve_plan
from mapf.core.models import (
    Conflict,
    ConflictType,
    Point,
    RecordingLevel,
    SimulationConfig,
)
from mapf.engine.world import WorldSimulation


def scene(level=RecordingLevel.FULL_TRACE, limit=250000):
    collector = TraceCollector()
    world = WorldSimulation(
        SimulationConfig(
            grid_width=6,
            grid_height=6,
            fov_size=5,
            recording_level=level,
            heat_recording_limit=limit,
            enable_telemetry=True,
            telemetry_hook=collector,
        )
    )
    for aid, start, target in [
        ("a", Point(1, 1), Point(1, 5)),
        ("b", Point(2, 1), Point(2, 5)),
        ("c", Point(1, 2), Point(5, 2)),
    ]:
        world.add_agent(HeatMapAgent(aid, start, target, fov_size=5))
    world.initialize()
    conflict = Conflict(
        agent_a="a",
        agent_b="b",
        time=0,
        conflict_type=ConflictType.VERTEX,
        location_a=Point(1, 2),
    )
    return world, collector, conflict


def test_records_known_kernel_and_multiple_contexts_without_mutating_old_snapshots():
    world, collector, conflict = scene()
    a = world.agents["a"]
    a.on_pre_negotiation("b", conflict, world.for_agent("a"), 0)
    world.record_decision_heat(a, 0, "session-one")
    first = world._heat_recorder.records[0]
    assert first["fields"][0]["1-2"] == 1.0
    assert first["fields"][0]["2-2"] == pytest.approx(2 / 3)
    assert first["opponent_id"] == "b"
    assert first["tick"] == 0 and first["source"] == "actual_strategy_weights"
    a.on_pre_negotiation("c", conflict, world.for_agent("a"), 0)
    world.record_decision_heat(a, 0, "session-two")
    second = world._heat_recorder.records[1]
    assert second["fields"][0]["2-1"] == 1.0
    assert first["fields"][0]["1-2"] == 1.0
    assert second["session_id"] != first["session_id"]
    assert [event["event_type"] for event in collector.events].count(
        "DECISION_HEAT"
    ) == 2


@pytest.mark.parametrize("level", [RecordingLevel.METRICS_ONLY, RecordingLevel.EVENTS])
def test_non_full_recording_never_materializes_heat_fields(level, monkeypatch):
    world, collector, conflict = scene(level)
    agent = world.agents["a"]
    agent.on_pre_negotiation("b", conflict, world.for_agent("a"), 0)

    def forbidden():
        raise AssertionError("No heat snapshot construction in this recording mode")

    monkeypatch.setattr(agent, "decision_heat_values", forbidden)
    world.record_decision_heat(agent, 0, "session")
    assert not world._heat_recorder.records
    assert not any(e["event_type"] == "DECISION_HEAT" for e in collector.events)


def test_recording_budget_is_explicit_and_preserves_behavior():
    world, _collector, conflict = scene(limit=0)
    agent = world.agents["a"]
    agent.on_pre_negotiation("b", conflict, world.for_agent("a"), 0)
    before = dict(agent._cell_weights)
    world.record_decision_heat(agent, 0, "session")
    record = world._heat_recorder.records[0]
    assert record["status"] == "budget_exhausted"
    assert record["fields"] == [] and record["aggregate"] == {}
    assert record["required_entries"] > 0 and record["recorded_entries"] == 0
    assert dict(agent._cell_weights) == before


def test_solver_replay_preserves_decision_time_fields_and_legacy_frames_remain_readable():
    request = JobSubmissionRequest(
        grid_width=5,
        grid_height=5,
        starts={"a": [0, 2], "b": [4, 2], "c": [2, 0]},
        goals={"a": [4, 2], "b": [0, 2], "c": [2, 4]},
        setting="SETTING_4",
        solver_id="Decentralized-HeatMap",
        fov_size=5,
        initial_tokens=5,
        timeout_sec=None,
        max_steps=32,
        recording_level="full-trace",
    )
    execution = solve_plan(preview(request))
    result = execution["result"]
    assert result["success"]
    records = [(f["tick"], h) for f in result["frames"] for h in f["local_heat"]]
    assert records and all(h["tick"] == t - 1 for t, h in records)
    assert any(any(field for field in h["fields"]) for _, h in records)
    assert any(e["event_type"] == "DECISION_HEAT" for e in result["telemetry_events"])
    frame = dict(result["frames"][0])
    frame.pop("local_heat")
    assert FrameSnapshot.model_validate(frame).local_heat == []


def test_heat_budget_bounds_headers_and_reports_omissions_per_step():
    from mapf.core.heat import HeatRecorder

    world, _, conflict = scene()
    agent = world.agents["a"]
    agent.on_pre_negotiation("b", conflict, world.for_agent("a"), 0)
    recorder = HeatRecorder(True, 10000, record_limit=1)
    recorder.capture(agent, 0, "first")
    recorder.capture(agent, 0, "second")
    records, omitted = recorder.drain()
    assert len(records) == 1 and omitted == 1
    assert recorder.drain() == ([], 0)
    recorder.capture(agent, 1, "third")
    assert recorder.drain() == ([], 1)
    assert recorder.omitted == 2


def test_persistence_checked_import_and_offline_export_preserve_exact_fields(tmp_path):
    import time

    from mapf.application.artifacts import export_bundle, import_bundle, standalone_html
    from mapf.application.jobs import completed_payload
    from mapf.application.plans import provenance
    from mapf.application.runs import RunRepository, new_id

    request = JobSubmissionRequest(
        grid_width=5,
        grid_height=5,
        starts={"a": [0, 2], "b": [4, 2], "c": [2, 0]},
        goals={"a": [4, 2], "b": [0, 2], "c": [2, 4]},
        setting="SETTING_4",
        solver_id="Decentralized-HeatMap",
        fov_size=5,
        timeout_sec=None,
        max_steps=32,
        recording_level="full-trace",
    )
    plan = preview(request)
    plan["provenance"] = provenance()
    job = {
        "job_id": new_id("job"),
        "run_id": new_id("run"),
        "attempt_id": new_id("attempt"),
        "definition_digest": plan["definition_digest"],
        "plan": plan,
        "effective_config": plan["effective_config"],
        "created_at": time.time(),
        "started_at": time.time(),
    }
    payload = completed_payload(job, solve_plan(plan))
    repository = RunRepository(tmp_path)
    repository.save_run(payload)
    loaded = repository.get_run(job["run_id"])
    assert loaded["frames"] == payload["frames"]
    imported = repository.get_run(import_bundle(export_bundle(loaded), repository))
    assert imported["frames"] == payload["frames"]
    document = standalone_html(imported)
    assert 'id="heat-slice"' in document and "actual_strategy_weights" in document
    assert 'src="http' not in document
