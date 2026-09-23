"""Retained profiling fixtures; the command-line runner is retired.

Use scripts/qualify_performance.py for bounded resource and recording checks,
or mapf batch for a planned study.
"""

from __future__ import annotations

import time
import tracemalloc
from typing import Any

from mapf.agents.heatmap import HeatMapAgent
from mapf.core.models import Point, RecordingLevel, SimulationConfig, SimulationSetting
from mapf.core.solution_validator import validate_solution
from mapf.engine.world import WorldSimulation
from mapf.solvers.base import MAPFInstance


def profile_case(
    name: str,
    width: int,
    height: int,
    starts: dict[str, Point],
    goals: dict[str, Point],
    obstacles: set[Point],
    level: RecordingLevel,
) -> dict[str, Any]:
    cfg = SimulationConfig(
        grid_width=width,
        grid_height=height,
        obstacles=obstacles,
        setting=SimulationSetting.SETTING_4,
        max_steps=50,
        random_seed=42,
        recording_level=level,
    )

    tracemalloc.start()
    t0_wall = time.perf_counter()
    t0_cpu = time.process_time()

    sim = WorldSimulation(cfg)
    for aid, s in starts.items():
        sim.add_agent(
            HeatMapAgent(aid, s, goals[aid], cfg.initial_tokens, cfg.fov_size)
        )

    res = sim.run()

    t1_cpu = time.process_time()
    t1_wall = time.perf_counter()
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Validate physical solution
    inst = MAPFInstance(
        grid_width=width,
        grid_height=height,
        starts=starts,
        goals=goals,
        obstacles=obstacles,
    )
    from mapf.core.models import Path as MAPFPath

    executed_paths = {
        aid: MAPFPath(points=pts) for aid, pts in res["path_history"].items()
    }
    val = validate_solution(inst, executed_paths, cfg.setting)

    return {
        "case": name,
        "recording_level": level.value,
        "agents": len(starts),
        "wall_time_ms": round((t1_wall - t0_wall) * 1000.0, 2),
        "cpu_time_ms": round((t1_cpu - t0_cpu) * 1000.0, 2),
        "peak_mem_kib": round(peak / 1024.0, 2),
        "success": res["success"],
        "valid": val.is_valid,
        "frames_retained": len(res.get("frames", [])),
    }


def run_profiling() -> list[dict[str, Any]]:
    cases = [
        (
            "sparse_2x2_swap",
            4,
            4,
            {"A": Point(x=0, y=0), "B": Point(x=3, y=3)},
            {"A": Point(x=3, y=3), "B": Point(x=0, y=0)},
            set(),
        ),
        (
            "corridor_crossing",
            8,
            3,
            {"A": Point(x=0, y=1), "B": Point(x=7, y=1)},
            {"A": Point(x=7, y=1), "B": Point(x=0, y=1)},
            {Point(x=x, y=0) for x in range(8)} | {Point(x=x, y=2) for x in range(8)},
        ),
        (
            "dense_8_agents_16x16",
            12,
            12,
            {f"A{i}": Point(x=i, y=0) for i in range(6)},
            {f"A{i}": Point(x=11 - i, y=11) for i in range(6)},
            {Point(x=4, y=4), Point(x=4, y=5), Point(x=7, y=6), Point(x=7, y=7)},
        ),
    ]

    results = []
    print(
        f"{'Case':<22} | {'Level':<12} | {'Wall (ms)':<10} | {'Peak (KiB)':<10} | {'Valid':<5} | {'Frames'}"
    )
    print("-" * 75)

    for name, w, h, starts, goals, obs in cases:
        for level in [
            RecordingLevel.METRICS_ONLY,
            RecordingLevel.EVENTS,
            RecordingLevel.FULL_TRACE,
        ]:
            r = profile_case(name, w, h, starts, goals, obs, level)
            results.append(r)
            print(
                f"{r['case']:<22} | {r['recording_level']:<12} | {r['wall_time_ms']:<10} | "
                f"{r['peak_mem_kib']:<10} | {r['valid']!s:<5} | {r['frames_retained']}"
            )

    return results


if __name__ == "__main__":
    raise SystemExit(
        "Archived unqualified runner. Use mapf batch plan/run/analyze; see docs/EXPERIMENTS.md. Historical outputs are preserved."
    )
    run_profiling()
