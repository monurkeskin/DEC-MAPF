"""Unit tests for post-simulation analytics engine."""

from __future__ import annotations

import polars as pl

from mapf.analytics.post_simulation import (
    analyze_rejection_reasons,
    compute_agent_wait_dynamics,
    compute_concession_curves,
    compute_spatial_hotspots,
    compute_token_inequality_gini,
    extract_keyframes,
    extract_manifest,
)


def test_spatial_hotspots() -> None:
    events = pl.DataFrame([
        {"event_type": "NEGO_SESSION", "conflict_x": 4, "conflict_y": 5},
        {"event_type": "NEGO_SESSION", "conflict_x": 4, "conflict_y": 5},
        {"event_type": "NEGO_SESSION", "conflict_x": 2, "conflict_y": 3},
        {"event_type": "MOVE", "x": 0, "y": 0},
    ])

    hotspots = compute_spatial_hotspots(events, grid_width=10, grid_height=10)
    assert hotspots["total_conflicts"] == 3
    assert len(hotspots["top_chokepoints"]) == 2
    top = hotspots["top_chokepoints"][0]
    assert top["x"] == 4
    assert top["y"] == 5
    assert top["conflicts"] == 2


def test_concession_curves() -> None:
    events = pl.DataFrame([
        {"event_type": "BID", "round_idx": 1, "offered_utility": 0.8},
        {"event_type": "BID", "round_idx": 1, "offered_utility": 0.7},
        {"event_type": "BID", "round_idx": 2, "offered_utility": 0.5},
        {"event_type": "BID", "round_idx": 2, "offered_utility": 0.4},
    ])

    curve = compute_concession_curves(events)
    assert curve["rounds"] == [1, 2]
    assert curve["mean_utility"] == [0.75, 0.45]


def test_token_inequality_gini() -> None:
    # Perfect equality: no transfers
    equal_events = pl.DataFrame([
        {"event_type": "MOVE", "x": 1, "y": 1},
    ])
    gini_equal = compute_token_inequality_gini(
        equal_events,
        initial_tokens=5,
        agent_ids=["a0", "a1", "a2", "a3"],
    )
    assert gini_equal["gini_coefficient"] == 0.0

    # Extreme inequality: transfers enrich one agent
    unequal_events = pl.DataFrame([
        {"event_type": "TOKEN_TRANSFER", "payer": "a0", "payee": "a1", "amount": 5,
         "balances_before": {"a0": 5, "a1": 5}, "balances_after": {"a0": 0, "a1": 10}},
        {"event_type": "TOKEN_TRANSFER", "payer": "a2", "payee": "a1", "amount": 5,
         "balances_before": {"a2": 5, "a1": 10}, "balances_after": {"a2": 0, "a1": 15}},
    ])
    gini_unequal = compute_token_inequality_gini(
        unequal_events,
        initial_tokens=5,
        agent_ids=["a0", "a1", "a2"],
    )
    # a0 has 0, a2 has 0, a1 has 15 -> severe inequality
    assert gini_unequal["gini_coefficient"] > 0.5


def test_agent_wait_dynamics() -> None:
    events = pl.DataFrame([
        {"event_type": "MOVE", "agent_id": "a0", "is_waiting": False},
        {"event_type": "MOVE", "agent_id": "a0", "is_waiting": True},
        {"event_type": "MOVE", "agent_id": "a1", "is_waiting": False},
        {"event_type": "MOVE", "agent_id": "a1", "is_waiting": False},
    ])

    waits = compute_agent_wait_dynamics(events)
    assert waits["agent_wait_ratios"]["a0"] == 0.5
    assert waits["agent_wait_ratios"]["a1"] == 0.0
    assert waits["max_wait_agent"] == "a0"


def test_extract_manifest_and_rejections() -> None:
    events = pl.DataFrame([
        {
            "event_type": "MANIFEST",
            "git_commit": "abc1234",
            "random_seed": 42,
            "grid_width": 16,
            "grid_height": 16,
            "agent_count": 20,
            "setting": "SETTING_4",
            "commitment": "SC",
            "fov_size": 5,
            "obstacles_count": 0,
            "timestamp": 12345678.0,
        },
        {
            "event_type": "NEGO_SESSION",
            "outcome": "FAILED",
            "reject_reason": "STATIONARY_IMPASSE",
        },
        {
            "event_type": "NEGO_SESSION",
            "outcome": "FAILED",
            "reject_reason": "INSUFFICIENT_UTILITY",
        },
        {
            "event_type": "NEGO_SESSION",
            "outcome": "AGREED",
            "reject_reason": "NONE",
        },
        {
            "event_type": "KEYFRAME",
            "tick": 25,
            "agent_states": {"a0": {"pos": [1, 2]}},
        },
    ])

    manifest = extract_manifest(events)
    assert manifest["git_commit"] == "abc1234"
    assert manifest["agent_count"] == 20

    rejections = analyze_rejection_reasons(events)
    assert rejections["total_sessions"] == 3
    assert rejections["failed_sessions"] == 2
    assert rejections["breakdown"]["STATIONARY_IMPASSE"] == 1
    assert rejections["breakdown"]["INSUFFICIENT_UTILITY"] == 1

    keyframes = extract_keyframes(events)
    assert len(keyframes) == 1
    assert keyframes[0]["tick"] == 25
