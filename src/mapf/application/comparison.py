"""Explicit unit matching and descriptive paired analysis (never row-index pairing)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mapf.application.runs import RunRepository, digest

METRICS = ("sum_of_costs", "makespan", "runtime_ms")
ALLOWED_TREATMENTS = frozenset({
    "solver_id", "commitment_type", "fov_size", "initial_tokens", "recording_level",
    "suboptimality", "timeout_sec", "negotiation_deadline_sec", "max_steps",
    "negotiation_round_limit", "verification_pass_limit", "max_astar_expansions",
})


def compare_runs(repository: RunRepository, left: list[str], right: list[str],
                 treatment_keys: Sequence[str]) -> dict[str, Any]:
    if set(left) & set(right):
        raise ValueError("A run cannot occur in both comparison groups")
    differences = set(treatment_keys)
    if not differences:
        raise ValueError("Declare at least one treatment key")
    if differences - ALLOWED_TREATMENTS:
        raise ValueError("Treatment keys must be solver parameters; seed, scenario and agent order remain pairing keys")
    cohort = _PairedCohort(_index_runs(repository, left, differences), _index_runs(repository, right, differences))
    return {"protocol": "paired-descriptive-v1", "treatment_keys": treatment_keys,
            "attempted": {"left": len(left), "right": len(right)}, **cohort.summary(),
            "uncertainty": "Descriptive paired sample only. No population CI or p-value: independent sampling units have not been established.",
            "denominator_policy": "Persisted completed attempts selected here; queued, cancelled, infrastructure failures and timeouts appear in Jobs, not silently as solved runs.",
            "rows": cohort.rows}


def _index_runs(repository: RunRepository, ids: list[str], differences: set[str]) -> dict[str, dict[str, Any]]:
    rows = {}
    for run_id in ids:
        run = repository.get_run(run_id, include_frames=False)
        if run is None:
            raise KeyError(run_id)
        meta = run["metadata"]
        identity = {"instance_hash": meta["instance_hash"],
                    "config": {k: v for k, v in meta["effective_config"].items() if k not in differences},
                    "metric_version": meta["metric_version"],
                    "source_sha256": meta["provenance"]["source_sha256"]}
        key = digest(identity)
        if key in rows:
            raise ValueError("Repeated attempt for one analysis unit; select one attempt explicitly")
        rows[key] = meta
    return rows


def _valid_solution(meta: dict[str, Any]) -> bool:
    return bool(meta["success"] and meta["is_valid"])


class _PairedCohort:
    """Keep pairing, qualification and cost denominators in the same cohort."""

    def __init__(self, left: dict[str, dict[str, Any]], right: dict[str, dict[str, Any]]) -> None:
        self.left, self.right = left, right
        self.paired = sorted(left.keys() & right.keys())
        self.left_solved = {key for key in self.paired if _valid_solution(left[key])}
        self.right_solved = {key for key in self.paired if _valid_solution(right[key])}
        self.common = self.left_solved & self.right_solved
        self.rows = [self._row(key) for key in self.paired]

    def _row(self, key: str) -> dict[str, Any]:
        x, y = self.left[key], self.right[key]
        cfgx, cfgy = x["effective_config"], y["effective_config"]
        return {"unit_id": key, "left_run_id": x["run_id"], "right_run_id": y["run_id"],
                "common_solved": key in self.common, "instance_hash": x["instance_hash"],
                "differences": {k: [cfgx.get(k), cfgy.get(k)] for k in cfgx.keys() | cfgy.keys()
                                if cfgx.get(k) != cfgy.get(k)},
                "deltas_right_minus_left": {m: y[m] - x[m] if key in self.common else None for m in METRICS}}

    def summary(self) -> dict[str, Any]:
        deltas = {m: [row["deltas_right_minus_left"][m] for row in self.rows if row["common_solved"]]
                  for m in METRICS}
        return {"paired": len(self.paired),
                "unmatched": {"left": len(self.left.keys() - self.right.keys()),
                              "right": len(self.right.keys() - self.left.keys())},
                "common_solved": len(self.common), "excluded_from_costs": len(self.paired) - len(self.common),
                "paired_coverage": self.coverage(),
                "means_right_minus_left": {m: sum(v) / len(v) if v else None for m, v in deltas.items()},
                "ranges_right_minus_left": {m: [min(v), max(v)] if v else None for m, v in deltas.items()}}

    def coverage(self) -> dict[str, int]:
        return {"both_solved": len(self.common), "left_only": len(self.left_solved - self.right_solved),
                "right_only": len(self.right_solved - self.left_solved),
                "neither_solved": len(set(self.paired) - self.left_solved - self.right_solved)}
