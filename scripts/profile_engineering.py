"""Bounded TAOP-v2 engineering profiles, not article-population experiments."""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import pstats
import time
import tracemalloc
from copy import deepcopy
from pathlib import Path

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.plans import preview, provenance
from mapf.application.runs import digest, encode
from mapf.application.worker import solve_plan


def specifications():
    return [
        {
            "name": "parallel-eight",
            "grid_width": 16,
            "grid_height": 12,
            "starts": {f"a{i}": [2 * i, 0] for i in range(8)},
            "goals": {f"a{i}": [2 * i, 8] for i in range(8)},
        },
        {
            "name": "crossing-two",
            "grid_width": 5,
            "grid_height": 5,
            "starts": {"a": [0, 2], "b": [2, 0]},
            "goals": {"a": [4, 2], "b": [2, 4]},
        },
        {
            "name": "crossing-three",
            "grid_width": 5,
            "grid_height": 5,
            "starts": {"a": [0, 2], "b": [4, 2], "c": [2, 0]},
            "goals": {"a": [4, 2], "b": [0, 2], "c": [2, 4]},
        },
    ]


def profile_plan(spec, level):
    return preview(
        JobSubmissionRequest(
            **spec,
            solver_id="Decentralized-HeatMap",
            setting="SETTING_4",
            recording_level=level,
            fov_size=5,
            initial_tokens=5,
            timeout_sec=None,
            max_steps=32,
            max_astar_expansions=1500,
            negotiation_protocol="taop-v2",
            negotiation_deadline_sec=60,
        )
    )


def measured_trial(name, level, repetition, plan):
    # Warmup is measured for auditing but excluded from reported timing summaries.
    begin, cpu = time.perf_counter(), time.process_time()
    execution = solve_plan(plan)
    wall, used_cpu = time.perf_counter() - begin, time.process_time() - cpu
    result = execution["result"]
    value = {
        k: deepcopy(result[k])
        for k in (
            "paths",
            "success",
            "validation",
            "measured_metrics",
            "negotiation_count",
        )
    }
    value["measured_metrics"]["solver_diagnostics"].pop("heat_recording", None)
    signature = digest(value)
    return {
        "fixture": name,
        "recording": level,
        "repetition": repetition,
        "warmup": repetition == -1,
        "wall_seconds": wall,
        "cpu_seconds": used_cpu,
        "signature": signature,
        "serialized_bytes": len(encode(execution)),
        "success": result["success"],
        "validation": result["validation"]["status"],
    }


def timing_replicates(identity, plan, repetitions, signatures):
    name, level = identity
    rows = []
    for repetition in range(-1, repetitions):
        row = measured_trial(name, level, repetition, plan)
        expected = signatures.setdefault(name, row["signature"])
        if row["signature"] != expected:
            raise AssertionError(f"Recording/repetition changed behavior: {name}")
        rows.append(row)
        print(json.dumps(row), flush=True)
    return rows


def instrumented_peak(plan, profile):
    # Instrumentation is separate from timing replicates.
    tracemalloc.start()
    profile.enable()
    execution = solve_plan(plan)
    profile.disable()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del execution  # Retain the measured result until the peak has been recorded.
    return peak


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 10:
        parser.error("Repetitions must be in 1..10")
    rows, signatures = [], {}
    profile = cProfile.Profile()
    for spec in specifications():
        for level in ("metrics-only", "full-trace"):
            plan = profile_plan(spec, level)
            rows.extend(
                timing_replicates(
                    (spec["name"], level), plan, args.repetitions, signatures
                )
            )
            rows[-1]["separate_instrumented_peak_bytes"] = instrumented_peak(
                plan, profile
            )
    stream = io.StringIO()
    pstats.Stats(profile, stream=stream).strip_dirs().sort_stats(
        "cumulative"
    ).print_stats(35)
    if args.compare:
        before = json.loads(args.compare.read_text())
        if before["signatures"] != signatures:
            raise AssertionError(
                "Baseline and candidate trajectories or measured metrics differ"
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "kind": "synthetic engineering qualification",
                "specifications": specifications(),
                "protocol": "taop-v2",
                "session_deadline_seconds": 60,
                "provenance": provenance(),
                "harness_sha256": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
                "timing_scope": "Warmup excluded; timing runs uninstrumented; cProfile and tracemalloc run separately. Other host workloads are not measured by this harness.",
                "signatures": signatures,
                "results": rows,
                "profile": stream.getvalue(),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
