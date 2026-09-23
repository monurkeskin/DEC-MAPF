#!/usr/bin/env python3
"""Read event telemetry and write a standalone HTML diagnostics report.

The report includes recorded conflict counts, offered utility summaries, token
balances, failure reasons and replay keyframe counts. Missing data stays
unavailable; replay keyframes are not solver checkpoints.
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

from mapf.analytics.diagnostics_report import format_metric, generate_html_report
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
    parser = argparse.ArgumentParser(description="Summarize Recorded Event Telemetry")
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

    print(f"\n[Diagnostics] Analyzing telemetry stream from: {events_file}")
    df = load_events_as_polars(events_file)
    print(f"  Loaded {len(df)} discrete events into Polars.")

    manifest = extract_manifest(df)
    hotspots = compute_spatial_hotspots(df, args.grid_size, args.grid_size)
    concessions = compute_concession_curves(df)
    gini_data = compute_token_inequality_gini(df)
    wait_data = compute_agent_wait_dynamics(df)
    rejection_data = analyze_rejection_reasons(df)
    keyframes = extract_keyframes(df)

    print("\n--- Summary Telemetry Insights ---")
    if manifest:
        print(
            f"  • Run Setting / Commit:        {manifest.get('setting')} / {manifest.get('git_commit')}"
        )
    print(f"  • Total Negotiation Conflicts: {hotspots['total_conflicts']}")
    print(
        f"  • Negotiation Success Rate:    {format_metric(rejection_data['success_rate'], '.1%')}"
    )
    print(
        f"  • Token Wealth Gini Index:     {format_metric(gini_data['gini_coefficient'], '.4f')}"
    )
    print(
        f"  • Mean Wait Ratio:             {format_metric(wait_data['mean_wait_ratio'], '.2%')}"
    )
    print(f"  • Replay Keyframes:            {len(keyframes)}")
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
