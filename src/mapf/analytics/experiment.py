"""All-planned denominators and paired, scenario-clustered descriptive inference."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from mapf.analytics._experiment_cohort import group_trials, select_trials, summarize
from mapf.analytics._experiment_pairing import PairedSamples
from mapf.application.runs import atomic_write, digest, encode


def analyze_experiment(
    rows: list[dict[str, Any]], left_solver: str, right_solver: str,
    *, filters: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    """Pair identical inputs, then resample independent scenario blocks, not agents.

    Population interpretation requires the caller's frozen sampling protocol.
    These intervals alone do not establish representative sampling or equivalence.
    """
    solvers = (left_solver, right_solver)
    selected = select_trials(rows, solvers, filters or {})
    groups = group_trials(selected, solvers)
    left, right = groups[left_solver], groups[right_solver]
    samples = PairedSamples.from_groups(left, right)
    return {
        "schema_version": "experiment-analysis-1", "left_solver": left_solver, "right_solver": right_solver,
        "left": summarize(left), "right": summarize(right), **samples.summaries(),
        "filters": filters or {}, "included_trial_ids": [row["trial_id"] for row in selected],
        "cohort_sha256": digest(selected),
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
    atomic_write(output / "summary.tex", _latex_summary(result))
    _plot_success(result, output)
    return _export_receipt(result, output)


def _escape_latex(value: str) -> str:
    mapping = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(mapping.get(c, c) for c in value)


def _latex_summary(result: dict[str, Any]) -> bytes:
    latex = [r"\begin{tabular}{lrrr}", r"Method & Planned & Solved & Success (\%) \\"]
    for side in ("left", "right"):
        summary = result[side]
        rate = f"{100 * summary['success_rate']:.2f}" if summary["success_rate"] is not None else "NA"
        latex.append(f"{_escape_latex(result[side + '_solver'])} & {summary['planned']} & {summary['solved']} & {rate}" + r" \\")
    latex.append(r"\end{tabular}")
    return "\n".join(latex).encode()


def _plot_success(result: dict[str, Any], output: Path) -> None:
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


def _export_receipt(result: dict[str, Any], output: Path) -> dict[str, Any]:
    import hashlib
    receipt = {"cohort_sha256": result["cohort_sha256"], "source_type": "empirical",
               "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"}}
    atomic_write(output / "manifest.json", encode(receipt))
    return receipt
