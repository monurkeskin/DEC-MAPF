"""Prepare bounded synthetic GUI examples; no scientific benchmark is run here.

The generated JSON specification is consumed by the ordinary ``mapf batch`` CLI.
Geometry, roster order and seeds are explicit. No historical data are sampled.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


def crossings() -> dict[str, Any]:
    """Forty separated crossing pairs, distributed across a 32 by 32 map."""
    tiles = [(x, y) for y in range(8) for x in range(8) if (x + y) % 3 != 0][:40]
    starts, goals = {}, {}
    for i, (x, y) in enumerate(tiles):
        x, y = 4 * x, 4 * y
        starts[f"agent_{2 * i}"] = [x, y + 1]
        goals[f"agent_{2 * i}"] = [x + 3, y + 1]
        starts[f"agent_{2 * i + 1}"] = [x + 1, y]
        goals[f"agent_{2 * i + 1}"] = [x + 1, y + 3]
    return {"name": "Crossing districts · 32x32 · 80 agents",
            "grid_width": 32, "grid_height": 32, "obstacles": [],
            "starts": starts, "goals": goals, "setting": "SETTING_4"}


def warehouse(size: int, agents: int, seed: int) -> dict[str, Any]:
    """A synthetic aisle map with distinct shuffled starts and goals."""
    obstacles = sorted({(x, y)
                        for sx in range(4, size - 5, 8)
                        for sy in range(4, size - 5, 8)
                        for x in range(sx, sx + 3)
                        for y in range(sy, sy + 5)})
    blocked = set(obstacles)
    free = [(x, y) for y in range(size) for x in range(size) if (x, y) not in blocked]
    rng = random.Random(seed)
    points = rng.sample(free, 2 * agents)
    return {"name": f"Warehouse aisles · {size}x{size} · {agents} agents",
            "grid_width": size, "grid_height": size,
            "obstacles": [list(p) for p in obstacles],
            "starts": {f"agent_{i}": list(p) for i, p in enumerate(points[:agents])},
            "goals": {f"agent_{i}": list(p) for i, p in enumerate(points[agents:])},
            "setting": "SETTING_4"}


def prepare(folder: Path) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    scenarios = {
        "crossings-32-80": crossings(),
        "warehouse-32-80": warehouse(32, 80, 917),
        "warehouse-64-100": warehouse(64, 100, 918),
    }
    for name, scenario in scenarios.items():
        (folder / f"{name}.json").write_text(json.dumps(scenario, indent=2) + "\n")
    jobs = [
        {**scenarios["crossings-32-80"], "solver_id": "Decentralized-HeatMap", "fov_size": 3},
        {**scenarios["warehouse-32-80"], "solver_id": "Prioritized"},
        {**scenarios["warehouse-64-100"], "solver_id": "Prioritized", "max_astar_expansions": 20000},
        {"scenario_id": "grid-8x8-8a", "solver_id": "Decentralized-HeatMap"},
        {"scenario_id": "grid-8x8-8a", "solver_id": "Decentralized-PathAware"},
        {"scenario_id": "crossing-2a", "solver_id": "Decentralized-HeatMap"},
    ]
    spec = {
        "name": "Synthetic documentation gallery",
        "scenarios": jobs,
        "defaults": {"setting": "SETTING_4", "max_steps": 160, "timeout_sec": 30,
                     "negotiation_deadline_sec": 60, "fov_size": 5,
                     "initial_tokens": 5, "commitment_type": "SC", "random_seed": 42,
                     "recording_level": "full-trace", "heat_recording_limit": 250000},
        "budget": {"workers": 1, "wall_seconds": 300, "max_trials": len(jobs),
                   "disk_mb": 1024, "threads_per_worker": 1},
        "sampling": {"population": "Constructed documentation illustrations only",
                     "independent_unit": "scenario geometry and roster",
                     "generalization": "none; no paper reproduction or performance claim"},
    }
    target = folder / "gallery-spec.json"
    target.write_text(json.dumps(spec, indent=2) + "\n")
    return {"spec": str(target), "scenarios": len(scenarios), "trials": len(jobs),
            "execution": "Not started. Use mapf batch plan followed by mapf batch run."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("runs/documentation"))
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2))


if __name__ == "__main__":
    main()
