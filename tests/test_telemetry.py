"""Unit tests for discrete telemetry events and asynchronous logger."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from mapf.telemetry.events import (
    AgentMoveEvent,
    BroadcastEvent,
    KeyframeEvent,
    ManifestEvent,
    NegotiationSessionEvent,
    OfferBidEvent,
)
from mapf.telemetry.hook import NullTelemetryHook
from mapf.telemetry.logger import AsyncExperimentLogger


def test_telemetry_event_serialization() -> None:
    move = AgentMoveEvent(
        tick=1, agent_id="agent_0", x=3, y=4, is_waiting=False, remaining_dist=5
    )
    d = move.to_dict()
    assert d["event_type"] == "MOVE"
    assert d["tick"] == 1
    assert d["agent_id"] == "agent_0"
    assert d["x"] == 3
    assert d["y"] == 4
    assert d["is_waiting"] is False

    manifest = ManifestEvent("git123", 42, 16, 16, 10, "SETTING_4", "SC", 5, 0, 100.0)
    assert manifest.to_dict()["event_type"] == "MANIFEST"

    keyframe = KeyframeEvent(0, {"a0": {"pos": [0, 0]}})
    assert keyframe.to_dict()["event_type"] == "KEYFRAME"


def test_null_telemetry_hook() -> None:
    hook = NullTelemetryHook()
    # Must execute with zero exceptions and zero side effects
    hook.on_manifest(ManifestEvent("git", 42, 8, 8, 2, "SETTING_4", "SC", 5, 0, 1.0))
    hook.on_keyframe(KeyframeEvent(0, {}))
    hook.on_move(AgentMoveEvent(1, "a0", 0, 0, False, 1))
    hook.on_bid(OfferBidEvent("s1", 1, 1, "a0", 5, 0.0, 0.2))
    hook.on_negotiation_end(
        NegotiationSessionEvent("s1", 1, "a0", "a1", 0, 0, 1, "AGREED", 1)
    )
    hook.on_broadcast(BroadcastEvent(1, "a0", 5, 10))


def test_async_logger_streaming(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    with AsyncExperimentLogger(output_dir=log_dir, run_id="test_run_001") as logger:
        hook = logger.hook
        hook.on_manifest(
            ManifestEvent("test_commit", 42, 16, 16, 2, "SETTING_4", "SC", 5, 0, 1.0)
        )
        hook.on_keyframe(KeyframeEvent(0, {"a0": {"pos": [0, 0]}}))
        hook.on_move(
            AgentMoveEvent(
                tick=0, agent_id="a0", x=0, y=0, is_waiting=False, remaining_dist=2
            )
        )
        hook.on_move(
            AgentMoveEvent(
                tick=1, agent_id="a0", x=1, y=0, is_waiting=False, remaining_dist=1
            )
        )
        hook.on_bid(OfferBidEvent("s1", 1, 1, "a0", 2, 0.0, 0.5))
        hook.on_negotiation_end(
            NegotiationSessionEvent("s1", 1, "a0", "a1", 1, 0, 1, "AGREED", 2)
        )
        hook.on_broadcast(BroadcastEvent(0, "a0", 5, 8))

    events_path = logger.events_file_path
    assert events_path.exists()

    # Read back gzip file
    lines = []
    with gzip.open(events_path, "rt", encoding="utf-8") as f:
        for line in f:
            lines.append(json.loads(line.strip()))

    assert len(lines) == 7
    types = [l["event_type"] for l in lines]
    assert "MANIFEST" in types
    assert "KEYFRAME" in types
    assert "MOVE" in types
    assert "BID" in types
    assert "NEGO_SESSION" in types
    assert "BROADCAST" in types


def test_recording_levels_behavior() -> None:
    """Keep solution behavior identical when metrics-only recording omits frames."""
    from mapf.agents.heatmap import HeatMapAgent
    from mapf.core.models import (
        Point,
        RecordingLevel,
        SimulationConfig,
        SimulationSetting,
    )
    from mapf.engine.world import WorldSimulation

    starts = {"A": Point(x=0, y=0), "B": Point(x=4, y=4)}
    goals = {"A": Point(x=4, y=4), "B": Point(x=0, y=0)}

    # 1. Run in FULL_TRACE mode
    cfg_full = SimulationConfig(
        grid_width=5,
        grid_height=5,
        setting=SimulationSetting.SETTING_4,
        max_steps=20,
        random_seed=42,
        recording_level=RecordingLevel.FULL_TRACE,
    )
    w_full = WorldSimulation(cfg_full)
    w_full.add_agent(
        HeatMapAgent(
            "A", starts["A"], goals["A"], cfg_full.initial_tokens, cfg_full.fov_size
        )
    )
    w_full.add_agent(
        HeatMapAgent(
            "B", starts["B"], goals["B"], cfg_full.initial_tokens, cfg_full.fov_size
        )
    )
    res_full = w_full.run()

    # 2. Run in METRICS_ONLY mode
    cfg_metrics = SimulationConfig(
        grid_width=5,
        grid_height=5,
        setting=SimulationSetting.SETTING_4,
        max_steps=20,
        random_seed=42,
        recording_level=RecordingLevel.METRICS_ONLY,
    )
    w_metrics = WorldSimulation(cfg_metrics)
    w_metrics.add_agent(
        HeatMapAgent(
            "A",
            starts["A"],
            goals["A"],
            cfg_metrics.initial_tokens,
            cfg_metrics.fov_size,
        )
    )
    w_metrics.add_agent(
        HeatMapAgent(
            "B",
            starts["B"],
            goals["B"],
            cfg_metrics.initial_tokens,
            cfg_metrics.fov_size,
        )
    )
    res_metrics = w_metrics.run()

    # Solution outcome must be strictly identical
    assert res_full["success"] == res_metrics["success"]
    assert res_full["collision_count"] == res_metrics["collision_count"]
    assert res_full["total_steps"] == res_metrics["total_steps"]
    assert res_full["total_path_length"] == res_metrics["total_path_length"]

    # Storage footprint must be different
    assert len(res_full["frames"]) > 0
    assert len(res_metrics["frames"]) == 0
    assert len(w_metrics.frames) == 0
