from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend for headless execution
import matplotlib.pyplot as plt


def generate_jaamas_comparison_plot(
    data: dict[str, list[float]],
    agent_counts: list[int],
    setting_name: str = "Setting 4 (Disappear=True, Wait=True)",
    output_path: str | Path = "solution_rate_comparison.svg",
) -> Path:
    """Plot caller-supplied success rates by agent count.

    The caller supplies qualified denominators; this function neither loads
    article data nor calculates uncertainty."""
    try:
        plt.style.use(["science", "no-latex"])
    except (OSError, ValueError, KeyError):
        plt.style.use("default")

    fig, ax = plt.subplots(figsize=(6.5, 4.2), dpi=300)

    markers = ["o", "s", "^", "D", "v"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

    for idx, (strategy, rates) in enumerate(data.items()):
        marker = markers[idx % len(markers)]
        color = colors[idx % len(colors)]
        ax.plot(
            agent_counts,
            rates,
            label=strategy,
            marker=marker,
            color=color,
            linewidth=1.8,
            markersize=6,
        )

    ax.set_title(f"MAPF Benchmark Solution Rate - {setting_name}", fontsize=11, fontweight="bold")
    ax.set_xlabel("Number of Agents ($k$)", fontsize=10)
    ax.set_ylabel("Solution Rate", fontsize=10)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xticks(agent_counts)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(frameon=True, fontsize=9)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, format=out.suffix.lstrip(".") or "svg")
    plt.close(fig)

    return out
