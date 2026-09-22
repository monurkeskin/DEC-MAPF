"""All-planned denominators and paired, scenario-clustered descriptive inference."""

from __future__ import annotations

import csv
import io
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.runs import atomic_write, digest, encode


def _solved(row: dict[str, Any]) -> bool:
    return bool(row.get("success") and row.get("state") == "completed"
                and row.get("validation_status") == "valid_solution")


def _interval(blocks: dict[str, list[float]], repetitions: int = 2000) -> list[float] | None:
    if len(blocks) < 2:
        return None
    means = [statistics.mean(blocks[key]) for key in sorted(blocks)]
    rng = random.Random(1729)
    draws = sorted(statistics.mean(rng.choices(means, k=len(means))) for _ in range(repetitions))
    return [draws[int(0.025 * repetitions)], draws[min(repetitions - 1, int(0.975 * repetitions))]]


def analyze_experiment(
    rows: list[dict[str, Any]], left_solver: str, right_solver: str,
    *, filters: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    """Pair identical inputs, then resample independent scenario blocks, not agents.

    Population interpretation requires the caller's frozen sampling protocol.
    These intervals alone do not establish representative sampling or equivalence.
    """
    if left_solver == right_solver:
        raise ValueError("Choose two distinct solver treatments")
    selected = [r for r in rows if r.get("solver_id") in (left_solver, right_solver)
                and all(r.get(k) in values for k, values in (filters or {}).items())]
    selected.sort(key=lambda row: row["trial_id"])
    if len({r["trial_id"] for r in selected}) != len(selected):
        raise ValueError("Duplicate trial ID in analysis")
    configuration = set(JobSubmissionRequest.model_fields) - {
        "name", "scenario_id", "starts", "goals", "obstacles", "solver_id", "grid_width", "grid_height"
    }
    groups: dict[str, dict[str, dict[str, Any]]] = {left_solver: {}, right_solver: {}}
    for row in selected:
        key = digest({"instance": row["instance_hash"], "source": row["source_sha256"],
                      "metric": row["metric_version"],
                      "config": {k: row.get(k) for k in sorted(configuration)}})
        group = groups[row["solver_id"]]
        if key in group:
            raise ValueError("Duplicate attempt for a pairing unit; select an explicit attempt")
        group[key] = row

    def summarize(group: dict[str, dict[str, Any]]) -> dict[str, Any]:
        values = list(group.values())
        blocks: dict[str, list[float]] = defaultdict(list)
        for row in values:
            blocks[row.get("sampling_unit", row["instance_hash"])].append(float(_solved(row)))
        outcomes = Counter("solved" if _solved(r) else "invalid" if r.get("validation_status") == "invalid"
                           else "not_solved" if r["state"] == "completed" else r["state"] for r in values)
        return {"planned": len(values), "solved": sum(_solved(r) for r in values),
                "success_rate": sum(_solved(r) for r in values) / len(values) if values else None,
                "scenario_weighted_success_rate": statistics.mean(statistics.mean(b) for b in blocks.values()) if blocks else None,
                "interval": _interval(blocks), "independent_units": len(blocks), "outcomes": dict(outcomes),
                "solved_runtime_ms": sorted(r["runtime_ms"] for r in values if _solved(r) and r.get("runtime_ms") is not None)}

    left, right = groups[left_solver], groups[right_solver]
    paired = sorted(left.keys() & right.keys())
    coverage = {"both_solved": 0, "left_only": 0, "right_only": 0, "neither": 0,
                "unpaired": len(left.keys() ^ right.keys())}
    successes: dict[str, list[float]] = defaultdict(list)
    costs: dict[str, list[float]] = defaultdict(list)
    pairs = []
    for key in paired:
        a, b = left[key], right[key]
        good_a, good_b = _solved(a), _solved(b)
        coverage["both_solved" if good_a and good_b else "left_only" if good_a else "right_only" if good_b else "neither"] += 1
        unit = a.get("sampling_unit", a["instance_hash"])
        if unit != b.get("sampling_unit", b["instance_hash"]):
            raise ValueError("Paired trials disagree on independent sampling unit")
        successes[unit].append(float(good_b) - float(good_a))
        delta = b["sum_of_costs"] - a["sum_of_costs"] if good_a and good_b else None
        if delta is not None:
            costs[unit].append(float(delta))
        pairs.append({"left_trial": a["trial_id"], "right_trial": b["trial_id"], "sampling_unit": unit,
                      "common_solved": good_a and good_b, "delta_right_minus_left": delta,
                      "paper_eq2_left": (a["sum_of_costs"] / min(a["sum_of_costs"], b["sum_of_costs"]) - 1)
                      if good_a and good_b and min(a["sum_of_costs"], b["sum_of_costs"]) > 0 else None,
                      "paper_eq2_right": (b["sum_of_costs"] / min(a["sum_of_costs"], b["sum_of_costs"]) - 1)
                      if good_a and good_b and min(a["sum_of_costs"], b["sum_of_costs"]) > 0 else None})
    return {
        "schema_version": "experiment-analysis-1", "left_solver": left_solver, "right_solver": right_solver,
        "left": summarize(left), "right": summarize(right), "coverage": coverage,
        "cost": {"mean_delta_right_minus_left": statistics.mean(statistics.mean(b) for b in costs.values()) if costs else None,
                 "interval": _interval(costs), "independent_units": len(costs)},
        "success_difference": {"estimate_right_minus_left": statistics.mean(statistics.mean(b) for b in successes.values()) if successes else None,
                               "interval": _interval(successes), "independent_units": len(successes)},
        "filters": filters or {}, "included_trial_ids": [r["trial_id"] for r in selected],
        "cohort_sha256": digest(selected), "pairs": pairs,
        "method": "Equal-weight scenario blocks; 2000 percentile bootstrap draws, seed 1729, nominal 95% interval",
        "scope": "Conditional on frozen sampling population. Repeated agents/ticks are not independent observations. No equivalence claim.",
        "runtime_policy": "Solved runtimes shown separately; timeout, invalid and missing counts retained. No uncensored runtime superiority claim.",
        "paper_eq2_reference": "Minimum among the two selected methods on each common-solved instance; not an optimality gap",
    }


def export_analysis(result: dict[str, Any], output: Path) -> dict[str, Any]:
    """One canonical table drives all scientific exports and their provenance."""
    output.mkdir(parents=True, exist_ok=True)
    atomic_write(output / "analysis.json", encode(result))
    stream = io.StringIO()
    pairs = result["pairs"]
    writer = csv.DictWriter(stream, fieldnames=list(pairs[0]) if pairs else ["left_trial", "right_trial"])
    writer.writeheader()
    writer.writerows(pairs)
    atomic_write(output / "paired-table.csv", stream.getvalue().encode())
    def escape(value: str) -> str:
        mapping = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
        return "".join(mapping.get(c, c) for c in value)
    latex = [r"\begin{tabular}{lrrr}", r"Method & Planned & Solved & Success (\%) \\"]
    for side in ("left", "right"):
        summary = result[side]
        rate = f"{100 * summary['success_rate']:.2f}" if summary["success_rate"] is not None else "NA"
        latex.append(f"{escape(result[side + '_solver'])} & {summary['planned']} & {summary['solved']} & {rate}" + r" \\")
    latex.append(r"\end{tabular}")
    atomic_write(output / "summary.tex", "\n".join(latex).encode())
    # Optional analysis extra, imported only for figure export.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4.5), layout="constrained")
    for x, side, color in ((0, "left", "#0072B2"), (1, "right", "#D55E00")):
        summary = result[side]
        estimate = summary["scenario_weighted_success_rate"]
        if estimate is not None:
            ax.scatter([x], [estimate], color=color, s=65, zorder=3)
            interval = summary["interval"]
            if interval:
                ax.vlines(x, interval[0], interval[1], color=color, linewidth=2)
            ax.annotate(f"{summary['solved']}/{summary['planned']} planned", (x, estimate), xytext=(0, 12), textcoords="offset points", ha="center")
    ax.set_xticks([0, 1], [result["left_solver"], result["right_solver"]])
    ax.set(xlim=(-0.5, 1.5), ylim=(-0.05, 1.15), ylabel="Scenario-weighted valid solution rate")
    ax.grid(axis="y", alpha=0.25)
    fig.supxlabel(f"Scenario cluster bootstrap; cohort {result['cohort_sha256'][:16]}", fontsize=8)
    for extension in ("svg", "pdf", "png"):
        fig.savefig(output / f"success.{extension}", dpi=160)
    plt.close(fig)
    import hashlib
    receipt = {"cohort_sha256": result["cohort_sha256"], "source_type": "empirical",
               "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"}}
    atomic_write(output / "manifest.json", encode(receipt))
    return receipt
