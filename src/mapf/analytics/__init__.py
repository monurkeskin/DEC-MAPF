"""Analyze saved run records, paired experiments and event telemetry."""

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

__all__ = [
    "analyze_rejection_reasons",
    "compute_agent_wait_dynamics",
    "compute_concession_curves",
    "compute_spatial_hotspots",
    "compute_token_inequality_gini",
    "extract_keyframes",
    "extract_manifest",
    "load_events_as_polars",
]
