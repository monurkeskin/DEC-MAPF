"""Select unique paired inputs and summarize independent scenario blocks."""

from __future__ import annotations

import random
import statistics
from collections import Counter, defaultdict
from typing import Any, cast

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.runs import digest

Trial = dict[str, Any]
Blocks = dict[str, list[float]]


def solved(row: Trial) -> bool:
    return bool(row.get("success") and row.get("state") == "completed"
                and row.get("validation_status") == "valid_solution")


def sampling_unit(row: Trial) -> str:
    return cast(str, row.get("sampling_unit", row["instance_hash"]))


def block_mean(blocks: Blocks) -> float | None:
    return statistics.mean(statistics.mean(block) for block in blocks.values()) if blocks else None


def interval(blocks: Blocks, repetitions: int = 2000) -> list[float] | None:
    if len(blocks) < 2:
        return None
    means = [statistics.mean(blocks[key]) for key in sorted(blocks)]
    rng = random.Random(1729)
    draws = sorted(statistics.mean(rng.choices(means, k=len(means))) for _ in range(repetitions))
    return [draws[int(0.025 * repetitions)], draws[min(repetitions - 1, int(0.975 * repetitions))]]


def select_trials(rows: list[Trial], solvers: tuple[str, str], filters: dict[str, list[Any]]) -> list[Trial]:
    if solvers[0] == solvers[1]:
        raise ValueError("Choose two distinct solver treatments")
    selected = [row for row in rows if row.get("solver_id") in solvers
                and all(row.get(key) in values for key, values in filters.items())]
    selected.sort(key=lambda row: row["trial_id"])
    if len({row["trial_id"] for row in selected}) != len(selected):
        raise ValueError("Duplicate trial ID in analysis")
    return selected


def pair_key(row: Trial) -> str:
    configuration = set(JobSubmissionRequest.model_fields) - {
        "name", "scenario_id", "starts", "goals", "obstacles", "solver_id", "grid_width", "grid_height"
    }
    return digest({"instance": row["instance_hash"], "source": row["source_sha256"],
                   "metric": row["metric_version"],
                   "config": {key: row.get(key) for key in sorted(configuration)}})


def group_trials(rows: list[Trial], solvers: tuple[str, str]) -> dict[str, dict[str, Trial]]:
    groups: dict[str, dict[str, Trial]] = {solver: {} for solver in solvers}
    for row in rows:
        key = pair_key(row)
        group = groups[row["solver_id"]]
        if key in group:
            raise ValueError("Duplicate attempt for a pairing unit; select an explicit attempt")
        group[key] = row
    return groups


def _outcome(row: Trial) -> str:
    if solved(row):
        return "solved"
    if row.get("validation_status") == "invalid":
        return "invalid"
    return "not_solved" if row["state"] == "completed" else row["state"]


def summarize(group: dict[str, Trial]) -> Trial:
    values = list(group.values())
    blocks: Blocks = defaultdict(list)
    for row in values:
        blocks[sampling_unit(row)].append(float(solved(row)))
    successes = sum(solved(row) for row in values)
    return {"planned": len(values), "solved": successes,
            "success_rate": successes / len(values) if values else None,
            "scenario_weighted_success_rate": block_mean(blocks), "interval": interval(blocks),
            "independent_units": len(blocks), "outcomes": dict(Counter(_outcome(row) for row in values)),
            "solved_runtime_ms": sorted(row["runtime_ms"] for row in values
                                        if solved(row) and row.get("runtime_ms") is not None)}
