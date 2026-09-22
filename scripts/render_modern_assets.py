#!/usr/bin/env python3
"""Render publication figures directly from modernized simulation datasets.

Generates high-resolution figures for the repository assets directly from
the empirical datasets in benchmarks/results/ without marketing embellishments.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import matplotlib.pyplot as plt
import polars as pl

# Configure matplotlib for clean, academic aesthetic
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 13,
    "lines.linewidth": 1.75,
    "lines.markersize": 6,
    "grid.linestyle": "--",
    "grid.alpha": 0.5,
})

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "benchmarks" / "results"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = {
    "HeatMap": "#1f77b4",     # Blue
    "PathAware": "#ff7f0e",   # Orange
    "Greedy": "#2ca02c",      # Green
    "Conceder": "#d62728",    # Red
}

SETTINGS = ["SETTING_1", "SETTING_2", "SETTING_3", "SETTING_4"]
SETTING_TITLES = [
    "Setting 1 (noWait, noDaT)",
    "Setting 2 (Wait, noDaT)",
    "Setting 3 (noWait, DaT)",
    "Setting 4 (Wait, DaT)",
]


def render_figure_05_solution_rate(df: pl.DataFrame) -> None:
    """Figure 5: Decentralized Solution Rate vs Agent Count across FoV 5, 7, 9."""
    fig, axes = plt.subplots(1, 4, figsize=(16, 3.8), sharey=True, dpi=200)

    for idx, s_name in enumerate(SETTINGS):
        ax = axes[idx]
        sub = df.filter((pl.col("setting_name") == s_name) & pl.col("solver").is_in(["HeatMap", "PathAware"]))

        for solv in ["HeatMap", "PathAware"]:
            for fov in [5, 7, 9]:
                data = (
                    sub.filter((pl.col("solver") == solv) & (pl.col("fov") == fov))
                    .group_by("k")
                    .agg(pl.col("success").mean().alias("rate"))
                    .sort("k")
                )
                if data.height > 0:
                    ls = "-" if solv == "HeatMap" else "--"
                    alpha = 1.0 if fov == 5 else (0.75 if fov == 7 else 0.5)
                    marker = "o" if fov == 5 else ("s" if fov == 7 else "^")
                    ax.plot(
                        data["k"].to_list(),
                        data["rate"].to_list(),
                        label=f"{solv} (FoV {fov})",
                        color=PALETTE[solv],
                        linestyle=ls,
                        alpha=alpha,
                        marker=marker,
                    )

        ax.set_title(SETTING_TITLES[idx])
        ax.set_xlabel("Number of Agents ($k$)")
        if idx == 0:
            ax.set_ylabel("Solution Rate")
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True)

    axes[0].legend(loc="lower left", fontsize=7, ncol=2)
    plt.tight_layout()
    out_file = ASSETS_DIR / "solution_rate_vs_density.png"
    fig.savefig(out_file)
    plt.close()
    print(f"  [Rendered] {out_file}")


def render_figure_06_path_difference(df: pl.DataFrame) -> None:
    """Normalized Path Difference vs Agent Count across Settings."""
    fig, axes = plt.subplots(1, 4, figsize=(16, 3.8), sharey=True, dpi=200)

    for idx, s_name in enumerate(SETTINGS):
        ax = axes[idx]
        sub = df.filter(
            (pl.col("setting_name") == s_name)
            & pl.col("solver").is_in(["HeatMap", "PathAware"])
            & (pl.col("success") == True)
        )

        for solv in ["HeatMap", "PathAware"]:
            for fov in [5, 7, 9]:
                data = (
                    sub.filter((pl.col("solver") == solv) & (pl.col("fov") == fov))
                    .group_by("k")
                    .agg((pl.col("norm_path_diff") * 100).mean().alias("npd"))
                    .sort("k")
                )
                if data.height > 0:
                    ls = "-" if solv == "HeatMap" else "--"
                    alpha = 1.0 if fov == 5 else (0.75 if fov == 7 else 0.5)
                    marker = "o" if fov == 5 else ("s" if fov == 7 else "^")
                    ax.plot(
                        data["k"].to_list(),
                        data["npd"].to_list(),
                        label=f"{solv} (FoV {fov})",
                        color=PALETTE[solv],
                        linestyle=ls,
                        alpha=alpha,
                        marker=marker,
                    )

        ax.set_title(SETTING_TITLES[idx])
        ax.set_xlabel("Number of Agents ($k$)")
        if idx == 0:
            ax.set_ylabel("Normalized Path Difference (%)")
        ax.grid(True)

    axes[0].legend(loc="upper left", fontsize=7, ncol=2)
    plt.tight_layout()
    out_file = ASSETS_DIR / "path_difference_comparison.png"
    fig.savefig(out_file)
    plt.close()
    print(f"  [Rendered] {out_file}")


def render_figure_07_negotiations(df: pl.DataFrame) -> None:
    """Average Number of Negotiations vs Agent Count across Settings."""
    fig, axes = plt.subplots(1, 4, figsize=(16, 3.8), sharey=True, dpi=200)

    for idx, s_name in enumerate(SETTINGS):
        ax = axes[idx]
        sub = df.filter((pl.col("setting_name") == s_name) & pl.col("solver").is_in(["HeatMap", "PathAware"]))

        for solv in ["HeatMap", "PathAware"]:
            for fov in [5, 7, 9]:
                data = (
                    sub.filter((pl.col("solver") == solv) & (pl.col("fov") == fov))
                    .group_by("k")
                    .agg(pl.col("negotiations").mean().alias("negos"))
                    .sort("k")
                )
                if data.height > 0:
                    ls = "-" if solv == "HeatMap" else "--"
                    alpha = 1.0 if fov == 5 else (0.75 if fov == 7 else 0.5)
                    marker = "o" if fov == 5 else ("s" if fov == 7 else "^")
                    ax.plot(
                        data["k"].to_list(),
                        data["negos"].to_list(),
                        label=f"{solv} (FoV {fov})",
                        color=PALETTE[solv],
                        linestyle=ls,
                        alpha=alpha,
                        marker=marker,
                    )

        ax.set_title(SETTING_TITLES[idx])
        ax.set_xlabel("Number of Agents ($k$)")
        if idx == 0:
            ax.set_ylabel("Average Negotiations")
        ax.grid(True)

    axes[0].legend(loc="upper left", fontsize=7, ncol=2)
    plt.tight_layout()
    out_file = ASSETS_DIR / "negotiations_across_density.png"
    fig.savefig(out_file)
    plt.close()
    print(f"  [Rendered] {out_file}")


def render_commitment_boxplots() -> None:
    """Commitment type path difference comparison (SC vs DC vs ZC)."""
    comm_file = RESULTS_DIR / "commitment_types_results.parquet"
    if not comm_file.exists():
        print("  [Skip] commitment_types_results.parquet not found")
        return

    df_comm = pl.read_parquet(comm_file)
    sub = df_comm.filter(pl.col("setting_name") == "SETTING_4")

    # Commitment Normalized Path Difference Boxplot
    fig, ax = plt.subplots(figsize=(6.5, 3.8), dpi=200)
    box_data = []
    labels = []
    colors = ["#bdd7e7", "#6baed6", "#2171b5"] * 3
    for c_type in ["SC", "DC", "ZC"]:
        for fov in [5, 7, 9]:
            vals = sub.filter((pl.col("commitment") == c_type) & (pl.col("fov") == fov))["norm_path_diff"].to_list()
            box_data.append([float(v) * 100 for v in vals])
            labels.append(f"{c_type}\nFoV {fov}")

    bp = ax.boxplot(box_data, tick_labels=labels, patch_artist=True)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.8)

    ax.set_title("Normalized Path Difference by Commitment Horizon (Setting 4, $k=80$)")
    ax.set_ylabel("Normalized Path Difference (%)")
    ax.grid(True)
    plt.tight_layout()
    out_file11 = ASSETS_DIR / "commitment_path_difference.png"
    fig.savefig(out_file11)
    plt.close()
    print(f"  [Rendered] {out_file11}")


def main() -> None:
    print("\n[Assets] Rendering modernized figures from empirical benchmark results...")
    matrix_file = RESULTS_DIR / "exhaustive_paper_matrix.parquet"
    if not matrix_file.exists():
        print(f"Error: {matrix_file} not found")
        return

    df = pl.read_parquet(matrix_file)
    print(f"  Loaded {len(df)} verified runs from {matrix_file.name}")

    render_figure_05_solution_rate(df)
    render_figure_06_path_difference(df)
    render_figure_07_negotiations(df)
    render_commitment_boxplots()
    print("[Assets] All modernized figure assets successfully updated!\n")


if __name__ == "__main__":
    main()
