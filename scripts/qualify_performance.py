"""Fixed bounded workload for resource and recording regression.

TAOP v1 is intentional: these fixtures use an offer cap, including a corridor
with no possible passing. V2 deadline/concession acceptance is tested separately.
These timings do not characterize v2 or an empirical research population.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import itertools
import json
import pstats
import time
import tracemalloc
from pathlib import Path

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.plans import preview, provenance
from mapf.application.runs import digest, encode
from mapf.application.worker import solve_plan


def sparse_fixture():
    return (
        "sparse",
        16,
        16,
        {f"a{i}": (i * 3, 0) for i in range(4)},
        {f"a{i}": (i * 3, 10) for i in range(4)},
        [],
    )


def dense_fixture():
    return (
        "dense",
        8,
        8,
        {f"a{i}": (i % 8, i // 8) for i in range(20)},
        {f"a{i}": (7 - i % 8, 7 - i // 8) for i in range(20)},
        [],
    )


def obstacles_fixture():
    return (
        "obstacles",
        12,
        12,
        {f"a{i}": (i, 0) for i in range(6)},
        {f"a{i}": (11 - i, 11) for i in range(6)},
        [(6, y) for y in range(1, 11) if y != 6],
    )


def corridor_fixture():
    return (
        "corridor",
        8,
        3,
        {"a": (0, 1), "b": (7, 1)},
        {"a": (7, 1), "b": (0, 1)},
        [(x, y) for x in range(8) for y in (0, 2)],
    )


def fixtures():
    yield from (
        sparse_fixture(),
        dense_fixture(),
        obstacles_fixture(),
        corridor_fixture(),
    )


def fixture_plan(fixture, level):
    _, width, height, starts, goals, obstacles = fixture
    return preview(
        JobSubmissionRequest(
            grid_width=width,
            grid_height=height,
            starts=starts,
            goals=goals,
            obstacles=obstacles,
            setting="SETTING_4",
            recording_level=level,
            max_steps=12,
            negotiation_round_limit=6,
            negotiation_protocol="taop-v1",
            verification_pass_limit=1,
            max_astar_expansions=600,
            random_seed=7301,
        )
    )


def measured_trial(fixture, level, repetition, profiler):
    name = fixture[0]
    plan = fixture_plan(fixture, level)
    tracemalloc.start()
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    if name == "dense" and level == "metrics-only" and repetition == 0:
        profiler.enable()
    execution = solve_plan(plan)
    profiler.disable()
    wall, cpu = time.perf_counter() - start_wall, time.process_time() - start_cpu
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result = execution["result"]
    signature = digest(
        {
            k: result[k]
            for k in (
                "paths",
                "success",
                "validation",
                "measured_metrics",
                "negotiation_count",
            )
        }
    )
    size = len(encode(execution))
    if peak > 256 * 1024**2 or size > 50 * 1024**2:
        raise AssertionError("Declared fixture memory/artifact budget exceeded")
    return {
        "fixture": name,
        "recording": level,
        "repetition": repetition,
        "negotiation_protocol": "taop-v1",
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "traced_peak_bytes": peak,
        "serialized_bytes": size,
        "frames": len(result["frames"]),
        "events": len(result["telemetry_events"]),
        "events_dropped": execution["trace"]["events_dropped"],
        "success": result["success"],
        "validation": result["validation"]["status"],
        "signature": signature,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    results = []
    profiler = cProfile.Profile()
    for fixture in fixtures():
        expected = None
        for level, repetition in itertools.product(
            ("metrics-only", "events", "full-trace"), range(2)
        ):
            row = measured_trial(fixture, level, repetition, profiler)
            if expected is None:
                expected = row["signature"]
            if row["signature"] != expected:
                raise AssertionError(
                    f"Recording/repetition changed the scientific result: {fixture[0]}/{level}"
                )
            results.append(row)
            print(json.dumps(row), flush=True)
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats(
        "cumulative"
    ).print_stats(25)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "kind": "software qualification fixtures; no population inference",
                "provenance": provenance(),
                "harness_sha256": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
                "measurement": "tracemalloc and one cProfile run add overhead; timings are not solver rankings",
                "results": results,
                "dense_profile": stream.getvalue(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
