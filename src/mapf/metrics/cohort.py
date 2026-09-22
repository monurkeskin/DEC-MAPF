from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PairedInstanceComparison(BaseModel):
    """Paired cost comparison for a single common-solved instance."""
    model_config = ConfigDict(frozen=True)

    instance_hash: str
    baseline_makespan: int
    test_makespan: int
    delta_makespan: int
    baseline_soc: int
    test_soc: int
    delta_soc: int
    optimality_gap: float
    baseline_runtime_ms: float
    test_runtime_ms: float


class CohortComparisonResult(BaseModel):
    """Complete paired common-solved cohort evaluation result."""
    model_config = ConfigDict(frozen=True)

    baseline_solver: str
    test_solver: str
    total_evaluated_instances: int
    baseline_solved_count: int
    test_solved_count: int
    common_solved_count: int
    baseline_only_count: int
    test_only_count: int
    neither_solved_count: int
    baseline_success_rate: float
    test_success_rate: float
    mean_delta_makespan: float | None = None
    mean_delta_soc: float | None = None
    mean_optimality_gap: float | None = None
    paired_comparisons: list[PairedInstanceComparison] = Field(default_factory=list)


def evaluate_common_solved_cohort(
    records: list[dict[str, Any]],
    baseline_solver: str,
    test_solver: str,
) -> CohortComparisonResult:
    """Evaluate path quality and optimality strictly on the common-solved instance set.

    Adheres to Review Section 5 (B03, B10):
    - Missing or failed runs are never treated as zero cost.
    - Path quality is computed only over instances where both solvers succeeded.
    - Full accounting of asymmetric successes is preserved.
    """
    baseline_by_hash: dict[str, dict[str, Any]] = {}
    test_by_hash: dict[str, dict[str, Any]] = {}
    all_hashes: set[str] = set()

    for r in records:
        h = r.get("instance_hash", "")
        if not h:
            continue
        all_hashes.add(h)
        s = r.get("solver_name", r.get("solver", ""))
        if s == baseline_solver:
            baseline_by_hash[h] = r
        elif s == test_solver:
            test_by_hash[h] = r

    baseline_solved = {h for h, r in baseline_by_hash.items() if bool(r.get("success", False))}
    test_solved = {h for h, r in test_by_hash.items() if bool(r.get("success", False))}

    common_solved = sorted(baseline_solved & test_solved)
    baseline_only = baseline_solved - test_solved
    test_only = test_solved - baseline_solved
    neither = all_hashes - (baseline_solved | test_solved)

    paired: list[PairedInstanceComparison] = []
    for h in common_solved:
        b_rec = baseline_by_hash[h]
        t_rec = test_by_hash[h]

        b_ms = int(b_rec.get("makespan", 0))
        t_ms = int(t_rec.get("makespan", 0))
        b_soc = int(b_rec.get("sum_of_costs", 0))
        t_soc = int(t_rec.get("sum_of_costs", 0))

        d_ms = t_ms - b_ms
        d_soc = t_soc - b_soc
        gap = (d_soc / b_soc) if b_soc > 0 else 0.0

        paired.append(
            PairedInstanceComparison(
                instance_hash=h,
                baseline_makespan=b_ms,
                test_makespan=t_ms,
                delta_makespan=d_ms,
                baseline_soc=b_soc,
                test_soc=t_soc,
                delta_soc=d_soc,
                optimality_gap=round(gap, 6),
                baseline_runtime_ms=float(b_rec.get("runtime_ms", 0.0)),
                test_runtime_ms=float(t_rec.get("runtime_ms", 0.0)),
            )
        )

    n_common = len(paired)
    mean_d_ms = sum(p.delta_makespan for p in paired) / n_common if n_common > 0 else None
    mean_d_soc = sum(p.delta_soc for p in paired) / n_common if n_common > 0 else None
    mean_gap = sum(p.optimality_gap for p in paired) / n_common if n_common > 0 else None

    total_inst = len(all_hashes)
    b_rate = (len(baseline_solved) / total_inst) if total_inst > 0 else 0.0
    t_rate = (len(test_solved) / total_inst) if total_inst > 0 else 0.0

    return CohortComparisonResult(
        baseline_solver=baseline_solver,
        test_solver=test_solver,
        total_evaluated_instances=total_inst,
        baseline_solved_count=len(baseline_solved),
        test_solved_count=len(test_solved),
        common_solved_count=n_common,
        baseline_only_count=len(baseline_only),
        test_only_count=len(test_only),
        neither_solved_count=len(neither),
        baseline_success_rate=round(b_rate, 4),
        test_success_rate=round(t_rate, 4),
        mean_delta_makespan=round(mean_d_ms, 4) if mean_d_ms is not None else None,
        mean_delta_soc=round(mean_d_soc, 4) if mean_d_soc is not None else None,
        mean_optimality_gap=round(mean_gap, 6) if mean_gap is not None else None,
        paired_comparisons=paired,
    )
