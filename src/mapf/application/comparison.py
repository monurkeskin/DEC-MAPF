"""Explicit unit matching and descriptive paired analysis (never row-index pairing)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mapf.application.runs import RunRepository, digest


def compare_runs(
    repository: RunRepository,
    left: list[str],
    right: list[str],
    treatment_keys: Sequence[str],
) -> dict[str, Any]:
    if set(left) & set(right):
        raise ValueError("A run cannot occur in both comparison groups")
    differences = set(treatment_keys)
    if not differences:
        raise ValueError("Declare at least one treatment key")
    allowed_treatments = {
        "solver_id",
        "commitment_type",
        "fov_size",
        "initial_tokens",
        "recording_level",
        "suboptimality",
        "timeout_sec",
        "negotiation_deadline_sec",
        "max_steps",
        "negotiation_round_limit",
        "verification_pass_limit",
        "max_astar_expansions",
    }
    if differences - allowed_treatments:
        raise ValueError(
            "Treatment keys must be solver parameters; seed, scenario and agent order remain pairing keys"
        )

    def index(ids: list[str]) -> dict[str, dict[str, Any]]:
        rows = {}
        for run_id in ids:
            run = repository.get_run(run_id, include_frames=False)
            if run is None:
                raise KeyError(run_id)
            meta = run["metadata"]
            cfg = meta["effective_config"]
            identity = {
                "instance_hash": meta["instance_hash"],
                "config": {k: v for k, v in cfg.items() if k not in differences},
                "metric_version": meta["metric_version"],
                "source_sha256": meta["provenance"]["source_sha256"],
            }
            key = digest(identity)
            if key in rows:
                raise ValueError(
                    "Repeated attempt for one analysis unit; select one attempt explicitly"
                )
            rows[key] = run
        return rows

    a, b = index(left), index(right)
    paired = sorted(a.keys() & b.keys())
    solved = [
        k
        for k in paired
        if a[k]["metadata"]["success"]
        and b[k]["metadata"]["success"]
        and a[k]["metadata"]["is_valid"]
        and b[k]["metadata"]["is_valid"]
    ]
    left_solved = {
        k
        for k in paired
        if a[k]["metadata"]["success"] and a[k]["metadata"]["is_valid"]
    }
    right_solved = {
        k
        for k in paired
        if b[k]["metadata"]["success"] and b[k]["metadata"]["is_valid"]
    }
    rows = []
    for key in paired:
        x, y = a[key]["metadata"], b[key]["metadata"]
        cfgx, cfgy = x["effective_config"], y["effective_config"]
        rows.append(
            {
                "unit_id": key,
                "left_run_id": x["run_id"],
                "right_run_id": y["run_id"],
                "common_solved": key in solved,
                "instance_hash": x["instance_hash"],
                "differences": {
                    k: [cfgx.get(k), cfgy.get(k)]
                    for k in cfgx.keys() | cfgy.keys()
                    if cfgx.get(k) != cfgy.get(k)
                },
                "deltas_right_minus_left": {
                    m: y[m] - x[m] if key in solved else None
                    for m in ("sum_of_costs", "makespan", "runtime_ms")
                },
            }
        )
    deltas = {
        m: [row["deltas_right_minus_left"][m] for row in rows if row["common_solved"]]
        for m in ("sum_of_costs", "makespan", "runtime_ms")
    }
    return {
        "protocol": "paired-descriptive-v1",
        "treatment_keys": treatment_keys,
        "attempted": {"left": len(left), "right": len(right)},
        "paired": len(paired),
        "unmatched": {
            "left": len(a.keys() - b.keys()),
            "right": len(b.keys() - a.keys()),
        },
        "common_solved": len(solved),
        "excluded_from_costs": len(paired) - len(solved),
        "paired_coverage": {
            "both_solved": len(solved),
            "left_only": len(left_solved - right_solved),
            "right_only": len(right_solved - left_solved),
            "neither_solved": len(set(paired) - left_solved - right_solved),
        },
        "means_right_minus_left": {
            m: sum(v) / len(v) if v else None for m, v in deltas.items()
        },
        "ranges_right_minus_left": {
            m: [min(v), max(v)] if v else None for m, v in deltas.items()
        },
        "uncertainty": "Descriptive paired sample only. No population CI or p-value: independent sampling units have not been established.",
        "denominator_policy": "Persisted completed attempts selected here; queued, cancelled, infrastructure failures and timeouts appear in Jobs, not silently as solved runs.",
        "rows": rows,
    }
