"""Spawn-safe worker and synchronous headless adapter. No HTTP or UI imports."""

from __future__ import annotations

import os
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mapf.application.plans import instance_from_snapshot, provenance
from mapf.application.replay import build_solver_run_result
from mapf.application.runs import atomic_write, encode
from mapf.application.solvers import SolverRegistry
from mapf.core.models import (
    CommitmentType,
    RecordingLevel,
    SimulationConfig,
    SimulationSetting,
)
from mapf.telemetry.hook import NullTelemetryHook
from mapf.telemetry.schema import SerializableEvent, normalize


class TraceCollector(NullTelemetryHook):
    """Bounded telemetry; overflow is reported rather than silently dropped."""

    def __init__(self, limit: int = 100000, context: dict[str, Any] | None = None) -> None:
        self.events: list[dict[str, Any]] = []
        self.limit = limit
        self.dropped = 0
        self.context = context or {}

    def capture(self, event: SerializableEvent) -> None:
        if len(self.events) < self.limit:
            value = normalize(event, len(self.events) + 1)
            value.update(self.context)
            self.events.append(value)
        else:
            self.dropped += 1

    on_manifest = capture
    on_keyframe = capture
    on_move = capture
    on_bid = capture
    on_negotiation_end = capture
    on_broadcast = capture
    on_diagnostic = capture


def solve_plan(plan: dict[str, Any], *, identity: dict[str, Any] | None = None,
               negotiation_lifecycle_hook: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    cfg = plan["effective_config"]
    snap = plan["scenario"]
    instance = instance_from_snapshot(snap)
    collector = TraceCollector(context={"source_sha256": plan.get("provenance", {}).get("source_sha256"),
                                       "definition_digest": plan["definition_digest"], **(identity or {})})
    config = SimulationConfig(
        grid_width=instance.grid_width,
        grid_height=instance.grid_height,
        obstacles=instance.obstacles,
        setting=SimulationSetting[cfg["setting"]],
        commitment_type=CommitmentType(cfg["commitment_type"]),
        max_steps=cfg["max_steps"],
        centralized_timeout_sec=cfg["timeout_sec"] if cfg["timeout_sec"] is not None else 60,
        negotiation_deadline_sec=cfg.get("negotiation_deadline_sec"),
        negotiation_lifecycle_hook=negotiation_lifecycle_hook,
        fov_size=cfg["fov_size"],
        broadcast_horizon=cfg.get("broadcast_horizon"),
        negotiation_horizon=cfg.get("negotiation_horizon"),
        negotiation_protocol=cfg.get("negotiation_protocol", "legacy-alternating-v1"),
        initial_tokens=cfg["initial_tokens"],
        random_seed=cfg["random_seed"],
        recording_level=RecordingLevel(cfg["recording_level"]),
        heat_recording_limit=cfg.get("heat_recording_limit", 250000),
        enable_telemetry=cfg["recording_level"] != "metrics-only",
        telemetry_hook=collector,
        negotiation_round_limit=cfg["negotiation_round_limit"],
        verification_pass_limit=cfg["verification_pass_limit"],
        max_astar_expansions=cfg["max_astar_expansions"],
    )
    solver = SolverRegistry.create_solver(
        cfg["solver_id"], cfg["timeout_sec"] if cfg["timeout_sec"] is not None else 60, cfg["suboptimality"],
        frozen_native_profile=cfg.get("native_profile"),
    )
    started = time.perf_counter()
    solution = solver.solve(instance, config)
    solve_ms = (time.perf_counter() - started) * 1000
    validating = time.perf_counter()
    result = build_solver_run_result(
        solver.name,
        cfg["solver_id"],
        instance,
        solution,
        config.setting,
        config.fov_size,
        config.initial_tokens,
        config.max_steps,
        include_frames=cfg["recording_level"] != "metrics-only",
    )
    result.runtime_ms = solve_ms
    result.instance_hash = snap["instance_hash"]
    result.telemetry_events = collector.events
    # Delivered information is available only for instrumented decentralized solvers.
    result.metric_availability["information_sharing_rate"] = "communication" in solution.metrics
    for event in result.telemetry_events:
        if event["event_type"] == "MANIFEST":
            event["git_commit"] = plan.get("provenance", {}).get(
                "git_commit", "unavailable"
            )
    result_data = result.model_dump(mode="json")
    return {
        "result": result_data,
        "timings": {
            "solver_ms": solve_ms,
            "validation_and_replay_ms": (time.perf_counter() - validating) * 1000,
        },
        "trace": {
            "recording_level": cfg["recording_level"],
            "events_dropped": collector.dropped,
            "heat_recording": solution.metrics.get("heat_recording", {"enabled": False}),
            "replay_kind": "visual replay only; no exact-resume checkpoint",
        },
        "legacy_metrics": {
            "reconstructed_IS_proxy": solution.metrics.get("legacy_reconstructed_IS_proxy")
        },
        "measured_metrics": result.measured_metrics,
        "execution_thread_limits": {key: os.environ.get(key, "unset") for key in (
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
            "NUMEXPR_NUM_THREADS", "POLARS_MAX_THREADS")},
    }


def execute_worker(job: dict[str, Any], output: str, *,
                   negotiation_lifecycle_hook: Callable[[dict[str, Any]], None] | None = None) -> None:
    # A pipe ties child lifetime to its supervisor; see JobSupervisor's watchdog wrapper.
    try:
        expected = job["plan"]["provenance"]["source_sha256"]
        if provenance()["source_sha256"] != expected:
            raise ValueError("Source changed after admission; create a new experiment identity")
        payload = solve_plan(job["plan"], identity={k: job[k] for k in ("job_id", "attempt_id", "run_id")},
                             negotiation_lifecycle_hook=negotiation_lifecycle_hook)
        payload["ok"] = True
    except Exception as exc:  # noqa: BLE001 - isolation boundary records worker/infrastructure failure
        payload = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    atomic_write(Path(output), encode(payload))


def owned_worker(job: dict[str, Any], output: str, parent_connection: Any) -> None:
    """Solver entry point; run_owned_process supplies the lifetime boundary."""
    # This process imports optional numerical libraries only after this entry point.
    # Bound their native pools independently from the process-worker limit.
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                     "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "POLARS_MAX_THREADS"):
        os.environ[variable] = "1"

    execute_worker(job, output, negotiation_lifecycle_hook=parent_connection.send)
