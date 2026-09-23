"""Summarize recorded conflicts, offered utilities, token balances and waits.

These summaries describe available events. A wait ratio alone does not
establish starvation, and missing utilities cannot produce a concession curve.
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
    return (
        frame.filter(pl.col("event_type") == kind)
        if "event_type" in frame.columns
        else pl.DataFrame()
    )


def _read_chunk(directory: Path, chunk: dict[str, Any]) -> list[dict[str, Any]]:
    name = chunk["file"]
    if Path(name).name != name:
        raise ValueError("Unsafe telemetry chunk name")
    raw = (directory / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != chunk["sha256"]:
        raise ValueError("Telemetry chunk integrity check failed")
    rows = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
    if len(rows) != chunk["count"]:
        raise ValueError("Telemetry chunk count mismatch")
    return rows


def _indexed_events(directory: Path) -> list[dict[str, Any]]:
    index = json.loads((directory / "index.json").read_text())
    records = []
    for chunk in index["chunks"]:
        records.extend(_read_chunk(directory, chunk))
    if len(records) != index["events"] or any(
        r["sequence"] != i + 1 for i, r in enumerate(records)
    ):
        raise ValueError("Telemetry event sequence is incomplete")
    return records


def load_events_as_polars(events_file_path: Path | str) -> pl.DataFrame:
    """Read plain, compressed or indexed JSON Lines with indexed integrity checks."""
    path = Path(events_file_path)
    if path.is_dir():
        records = _indexed_events(path)
    else:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as stream:
            records = [json.loads(line.strip()) for line in stream if line.strip()]
    return (
        pl.DataFrame(records, infer_schema_length=None) if records else pl.DataFrame()
    )


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

    chokepoints = [
        {"x": int(x), "y": int(y), "conflicts": int(matrix[y, x])}
        for y, x in np.argwhere(matrix > 0)
    ]

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
        .agg(
            [
                pl.col("offered_utility").mean().alias("mean_utility"),
                pl.col("offered_utility").std().alias("std_utility"),
                pl.len().alias("bid_count"),
            ]
        )
        .sort("round_idx")
    )

    rounds = grouped["round_idx"].to_list()
    mean_u = [round(float(u), 4) for u in grouped["mean_utility"].to_list()]
    std_u = [
        round(float(s), 4) if s is not None else 0.0
        for s in grouped["std_utility"].to_list()
    ]

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
    For n agents, the maximum is (n - 1) / n when one holds all tokens.
    """
    if initial_tokens < 0:
        raise ValueError("The initial token balance must be nonnegative")
    token_balance = dict.fromkeys(agent_ids or [], initial_tokens)
    roster = frozenset(agent_ids) if agent_ids else None
    transfers = _events(events_df, "TOKEN_TRANSFER")
    legacy = _events(events_df, "NEGO_SESSION")
    if transfers.is_empty() and not legacy.is_empty():
        return {
            "available": False,
            "gini_coefficient": None,
            "balances": {},
            "reason": "Legacy session events do not identify the actual payer; balances cannot be reconstructed",
        }
    for receipt in transfers.to_dicts():
        _apply_transfer(token_balance, receipt, roster)
    return _token_summary(token_balance, bool(agent_ids))


def _apply_transfer(
    balances: dict[str, int], receipt: dict[str, Any], roster: frozenset[str] | None
) -> None:
    before = _recorded_balances(receipt["balances_before"])
    after = _recorded_balances(receipt["balances_after"])
    _check_transfer_participants(before, after, roster)
    _check_transfer_totals(before, after)
    for agent, balance in before.items():
        if balances.get(agent, balance) != balance:
            raise ValueError("Token receipt does not match prior balance")
    balances.update(after)


def _recorded_balances(values: dict[str, Any]) -> dict[str, int]:
    # Polars unions struct keys across receipts, inserting nulls for absent agents.
    return {a: v for a, v in values.items() if v is not None}


def _check_transfer_participants(
    before: dict[str, int], after: dict[str, int], roster: frozenset[str] | None
) -> None:
    if before.keys() != after.keys():
        raise ValueError("Token receipt changes its participants")
    if roster is not None and not before.keys() <= roster:
        raise ValueError("Token receipt contains an undeclared participant")


def _check_transfer_totals(before: dict[str, int], after: dict[str, int]) -> None:
    if sum(before.values()) != sum(after.values()):
        raise ValueError("Token receipt violates conservation or overdraft invariant")
    if min((*before.values(), *after.values()), default=0) < 0:
        raise ValueError("Token receipt violates conservation or overdraft invariant")


def _token_summary(
    token_balance: dict[str, int], roster_complete: bool
) -> dict[str, Any]:
    values = np.array(list(token_balance.values()), dtype=np.float64)
    n = len(values)
    if n == 0:
        return {
            "available": False,
            "gini_coefficient": None,
            "balances": {},
            "reason": "No roster or token balances were recorded",
        }

    if np.sum(values) == 0:
        gini = 0.0
    else:
        diff_sum = np.sum(np.abs(values[:, None] - values[None, :]))
        gini = float(diff_sum / (2.0 * n * np.sum(values)))

    return {
        "available": True,
        "roster_complete": roster_complete,
        "gini_coefficient": round(gini, 4),
        "min_tokens": int(np.min(values)),
        "max_tokens": int(np.max(values)),
        "mean_tokens": round(float(np.mean(values)), 2),
        "balances": token_balance,
    }


def compute_agent_wait_dynamics(events_df: pl.DataFrame) -> dict[str, Any]:
    """Summarize recorded moves and waits; sustained waiting needs separate diagnosis."""
    move_events = _events(events_df, "MOVE")
    if move_events.is_empty():
        return {
            "available": False,
            "mean_wait_ratio": None,
            "max_wait_agent": None,
            "agent_wait_ratios": {},
        }

    summary = (
        move_events.group_by("agent_id")
        .agg(
            [
                pl.col("is_waiting").sum().alias("wait_count"),
                pl.len().alias("total_steps"),
            ]
        )
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
        "available": True,
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
        return {
            "available": False,
            "total_sessions": 0,
            "failed_sessions": 0,
            "success_rate": None,
            "breakdown": {},
        }

    failed = nego_events.filter(pl.col("outcome") == "FAILED")
    breakdown: dict[str, int] = {}
    if not failed.is_empty():
        counts = failed.group_by("reject_reason").len().to_dicts()
        for c in counts:
            breakdown[str(c["reject_reason"])] = int(c["len"])

    return {
        "available": True,
        "total_sessions": len(nego_events),
        "failed_sessions": len(failed),
        "success_rate": round(
            float(len(nego_events) - len(failed)) / max(1, len(nego_events)), 4
        ),
        "breakdown": breakdown,
    }


def extract_keyframes(events_df: pl.DataFrame) -> list[dict[str, Any]]:
    """Extract recorded replay keyframes; these are not solver checkpoints."""
    kf_events = _events(events_df, "KEYFRAME")
    if kf_events.is_empty():
        return []
    return kf_events.sort("tick").to_dicts()
