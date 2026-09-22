"""Post-Simulation Analytics Engine for Multi-Agent Path Finding.

Extracts quantitative metrics from discrete event telemetry:
1. Spatial Congestion Hotspots (2D conflict heat density matrix).
2. Bilateral Concession Dynamics (Utility degradation curves across rounds).
3. Token Wealth Inequality (Gini coefficient of token distribution).
4. Agent Velocity & Wait/Starvation distributions.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl


def _events(frame: pl.DataFrame, kind: str) -> pl.DataFrame:
    return frame.filter(pl.col("event_type") == kind) if "event_type" in frame.columns else pl.DataFrame()


def load_events_as_polars(events_file_path: Path | str) -> pl.DataFrame:
    """Read compressed JSON Lines event telemetry into a fast Polars DataFrame."""
    path = Path(events_file_path)
    records: list[dict[str, Any]] = []

    if path.is_dir():
        index = json.loads((path / "index.json").read_text())
        for chunk in index["chunks"]:
            name = chunk["file"]
            if Path(name).name != name:
                raise ValueError("Unsafe telemetry chunk name")
            raw = (path / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != chunk["sha256"]:
                raise ValueError("Telemetry chunk integrity check failed")
            rows = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
            if len(rows) != chunk["count"]:
                raise ValueError("Telemetry chunk count mismatch")
            records.extend(rows)
        if len(records) != index["events"] or any(r["sequence"] != i+1 for i, r in enumerate(records)):
            raise ValueError("Telemetry event sequence is incomplete")
        return pl.DataFrame(records, infer_schema_length=None) if records else pl.DataFrame()

    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    records.append(json.loads(line_str))
    else:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    records.append(json.loads(line_str))

    if not records:
        return pl.DataFrame()

    return pl.DataFrame(records, infer_schema_length=None)


def compute_spatial_hotspots(
    events_df: pl.DataFrame,
    grid_width: int,
    grid_height: int,
) -> dict[str, Any]:
    """Compute 2D spatial congestion matrix of negotiation conflict locations."""
    matrix = np.zeros((grid_height, grid_width), dtype=np.int32)

    nego_events = _events(events_df, "NEGO_SESSION")
    if nego_events.is_empty():
        return {
            "density_matrix": matrix.tolist(),
            "top_chokepoints": [],
            "total_conflicts": 0,
        }

    conflicts = nego_events.select(["conflict_x", "conflict_y"]).to_dicts()
    for c in conflicts:
        cx, cy = c["conflict_x"], c["conflict_y"]
        if 0 <= cx < grid_width and 0 <= cy < grid_height:
            matrix[cy, cx] += 1

    # Extract top choke points
    chokepoints = []
    for y in range(grid_height):
        for x in range(grid_width):
            count = int(matrix[y, x])
            if count > 0:
                chokepoints.append({"x": x, "y": y, "conflicts": count})

    chokepoints.sort(key=lambda item: item["conflicts"], reverse=True)

    return {
        "density_matrix": matrix.tolist(),
        "top_chokepoints": chokepoints[:10],
        "total_conflicts": len(conflicts),
    }


def compute_concession_curves(events_df: pl.DataFrame) -> dict[str, Any]:
    """Analyze concession dynamics: how offered utility evolves across negotiation rounds."""
    bid_events = _events(events_df, "BID")
    if "offered_utility" in bid_events.columns:
        bid_events = bid_events.filter(pl.col("offered_utility").is_not_null())
    if bid_events.is_empty():
        return {"rounds": [], "mean_utility": [], "std_utility": []}

    grouped = (
        bid_events.group_by("round_idx")
        .agg([
            pl.col("offered_utility").mean().alias("mean_utility"),
            pl.col("offered_utility").std().alias("std_utility"),
            pl.len().alias("bid_count"),
        ])
        .sort("round_idx")
    )

    rounds = grouped["round_idx"].to_list()
    mean_u = [round(float(u), 4) for u in grouped["mean_utility"].to_list()]
    std_u = [round(float(s), 4) if s is not None else 0.0 for s in grouped["std_utility"].to_list()]

    return {
        "rounds": rounds,
        "mean_utility": mean_u,
        "std_utility": std_u,
    }


def compute_token_inequality_gini(
    events_df: pl.DataFrame,
    initial_tokens: int = 5,
    agent_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Compute the economic Gini coefficient of token wealth across all agents.

    G = 0.0 indicates perfect equality (every agent has identical tokens).
    G = 1.0 indicates maximum inequality (one agent holds all tokens).
    """
    token_balance: dict[str, int] = {}
    if agent_ids:
        for aid in agent_ids:
            token_balance[aid] = initial_tokens

    transfers = _events(events_df, "TOKEN_TRANSFER")
    legacy = _events(events_df, "NEGO_SESSION")
    if transfers.is_empty() and not legacy.is_empty():
        return {"available": False, "gini_coefficient": None, "balances": {},
                "reason": "Legacy session events do not identify the actual payer; balances cannot be reconstructed"}
    for receipt in transfers.to_dicts():
        before, after = receipt["balances_before"], receipt["balances_after"]
        before = {a: value for a, value in before.items() if value is not None}
        after = {a: value for a, value in after.items() if value is not None}
        if sum(before.values()) != sum(after.values()) or any(v < 0 for v in after.values()):
            raise ValueError("Token receipt violates conservation or overdraft invariant")
        for agent, balance in before.items():
            if agent in token_balance and token_balance[agent] != balance:
                raise ValueError("Token receipt does not match prior balance")
        token_balance.update(after)

    values = np.array(list(token_balance.values()), dtype=np.float64)
    n = len(values)

    if n == 0 or np.sum(values) == 0:
        gini = 0.0
    else:
        # Standard Gini calculation
        diff_sum = np.sum(np.abs(values[:, None] - values[None, :]))
        gini = float(diff_sum / (2.0 * n * np.sum(values)))

    return {
        "available": True,
        "roster_complete": bool(agent_ids),
        "gini_coefficient": round(gini, 4),
        "min_tokens": int(np.min(values)) if n > 0 else initial_tokens,
        "max_tokens": int(np.max(values)) if n > 0 else initial_tokens,
        "mean_tokens": round(float(np.mean(values)), 2) if n > 0 else float(initial_tokens),
        "balances": token_balance,
    }


def compute_agent_wait_dynamics(events_df: pl.DataFrame) -> dict[str, Any]:
    """Compute wait ratios and velocity profiles across agents to detect starvation."""
    move_events = _events(events_df, "MOVE")
    if move_events.is_empty():
        return {"mean_wait_ratio": 0.0, "max_wait_agent": None, "agent_wait_ratios": {}}

    summary = (
        move_events.group_by("agent_id")
        .agg([
            pl.col("is_waiting").sum().alias("wait_count"),
            pl.len().alias("total_steps"),
        ])
        .with_columns(
            (pl.col("wait_count") / pl.col("total_steps")).alias("wait_ratio")
        )
    )

    ratios = {
        row["agent_id"]: round(float(row["wait_ratio"]), 4)
        for row in summary.to_dicts()
    }
    mean_val = summary["wait_ratio"].mean()
    mean_wait = float(mean_val) if mean_val is not None else 0.0  # type: ignore[arg-type]
    max_row = summary.sort("wait_ratio", descending=True).head(1).to_dicts()
    max_agent = max_row[0]["agent_id"] if max_row else None

    return {
        "mean_wait_ratio": round(mean_wait, 4),
        "max_wait_agent": max_agent,
        "agent_wait_ratios": ratios,
    }


def extract_manifest(events_df: pl.DataFrame) -> dict[str, Any]:
    """Extract environment provenance and run configuration from the manifest event."""
    m_events = _events(events_df, "MANIFEST")
    if m_events.is_empty():
        return {}
    return m_events.to_dicts()[0]


def analyze_rejection_reasons(events_df: pl.DataFrame) -> dict[str, Any]:
    """Categorize and quantify why bilateral negotiations resulted in impasse or failure."""
    nego_events = _events(events_df, "NEGO_SESSION")
    if nego_events.is_empty():
        return {"total_sessions": 0, "failed_sessions": 0, "success_rate": 1.0, "breakdown": {}}

    failed = nego_events.filter(pl.col("outcome") == "FAILED")
    breakdown: dict[str, int] = {}
    if not failed.is_empty():
        counts = failed.group_by("reject_reason").len().to_dicts()
        for c in counts:
            breakdown[str(c["reject_reason"])] = int(c["len"])

    return {
        "total_sessions": len(nego_events),
        "failed_sessions": len(failed),
        "success_rate": round(float(len(nego_events) - len(failed)) / max(1, len(nego_events)), 4),
        "breakdown": breakdown,
    }


def extract_keyframes(events_df: pl.DataFrame) -> list[dict[str, Any]]:
    """Extract all periodic full-state keyframe snapshots for instant seeking."""
    kf_events = _events(events_df, "KEYFRAME")
    if kf_events.is_empty():
        return []
    return kf_events.sort("tick").to_dicts()
