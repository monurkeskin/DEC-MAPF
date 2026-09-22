#!/usr/bin/env python3
"""Standalone Deep Diagnostics & Analytics Exporter for DEC-MAPF.

Ingests discrete event telemetry (.jsonl.gz or .jsonl) and produces:
1. Interactive, standalone HTML dashboard with SVG spatial congestion heatmaps,
   concession curves, token wealth Gini distributions, rejection reasons,
   and keyframe timeline checkpoints.
2. Academic LaTeX tables of spatial bottlenecks and concession dynamics.
3. Terminal summary tables with full provenance metadata.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src is in python path
repo_root = Path(__file__).resolve().parent.parent
src_dir = repo_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from mapf.analytics.diagnostics_report import generate_html_report
from mapf.analytics.post_simulation import (
    analyze_rejection_reasons,
    compute_agent_wait_dynamics,
    compute_concession_curves,
    compute_spatial_hotspots,
    compute_token_inequality_gini,
    extract_keyframes,
    extract_manifest,
    load_events_as_polars,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Deep Scientific Diagnostics from Event Telemetry"
    )
    parser.add_argument(
        "events_path", type=str, help="Path to events.jsonl.gz or events.jsonl"
    )
    parser.add_argument(
        "--grid-size", type=int, default=16, help="Grid dimension (default: 16)"
    )
    parser.add_argument(
        "--output", type=str, default=None, help="Output HTML file path"
    )
    args = parser.parse_args()

    events_file = Path(args.events_path)
    if not events_file.exists():
        print(f"Error: Telemetry file {events_file} does not exist.", file=sys.stderr)
        sys.exit(1)

    run_id = events_file.stem.replace("_events", "").replace(".jsonl", "")
    output_html = (
        Path(args.output)
        if args.output
        else events_file.parent / f"{run_id}_diagnostics.html"
    )

    print(f"\n[Deep Diagnostics] Analyzing telemetry stream from: {events_file}")
    df = load_events_as_polars(events_file)
    print(f"  Loaded {len(df)} discrete events into Polars.")

    # 1. Manifest
    manifest = extract_manifest(df)
    # 2. Hotspots
    hotspots = compute_spatial_hotspots(df, args.grid_size, args.grid_size)
    # 3. Concessions
    concessions = compute_concession_curves(df)
    # 4. Gini
    gini_data = compute_token_inequality_gini(df)
    # 5. Waits
    wait_data = compute_agent_wait_dynamics(df)
    # 6. Rejections
    rejection_data = analyze_rejection_reasons(df)
    # 7. Keyframes
    keyframes = extract_keyframes(df)

    print("\n--- Summary Telemetry Insights ---")
    if manifest:
        print(
            f"  • Run Setting / Commit:        {manifest.get('setting')} / {manifest.get('git_commit')}"
        )
    print(f"  • Total Negotiation Conflicts: {hotspots['total_conflicts']}")
    print(
        f"  • Negotiation Success Rate:    {rejection_data['success_rate'] * 100:.1f}%"
    )
    print(f"  • Token Wealth Gini Index:     {gini_data['gini_coefficient']:.4f}")
    print(f"  • Mean Wait Ratio:             {wait_data['mean_wait_ratio'] * 100:.2f}%")
    print(f"  • Checkpoint Keyframes:        {len(keyframes)}")
    if hotspots["top_chokepoints"]:
        print(
            f"  • Top Choke Point:             ({hotspots['top_chokepoints'][0]['x']}, {hotspots['top_chokepoints'][0]['y']}) with {hotspots['top_chokepoints'][0]['conflicts']} conflicts"
        )

    generate_html_report(
        run_id=run_id,
        manifest=manifest,
        hotspots=hotspots,
        concessions=concessions,
        gini_data=gini_data,
        wait_data=wait_data,
        rejection_data=rejection_data,
        keyframes=keyframes,
        grid_width=args.grid_size,
        grid_height=args.grid_size,
        output_html_path=output_html,
    )


if __name__ == "__main__":
    main()
