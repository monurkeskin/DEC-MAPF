"""Replay consumes real phase-aware receipts between sparse keyframes."""

import gzip
import json

import pytest

from mapf.telemetry.replay import DeterministicReplayEngine


def events():
    return [
        {"event_type": "KEYFRAME", "tick": 1, "schema_version": "telemetry-2", "phase": "post_move",
         "agent_states": {"a": {"pos": [0, 0], "target": [2, 0], "tokens": 5, "remaining_dist": 2},
                          "b": {"pos": [3, 0], "target": [3, 2], "tokens": 5, "remaining_dist": 2}}},
        {"event_type": "TOKEN_TRANSFER", "tick": 1, "phase": "pre_move", "schema_version": "telemetry-2",
         "payer": "a", "payee": "b", "amount": 2, "balances_before": {"a": 5, "b": 5},
         "balances_after": {"a": 3, "b": 7}},
        {"event_type": "MOVE", "tick": 2, "phase": "post_move", "schema_version": "telemetry-2",
         "agent_id": "a", "x": 1, "y": 0, "remaining_dist": 0},
    ]


def test_transfer_changes_tokens_at_the_following_post_move_frame():
    engine = DeterministicReplayEngine()
    engine.load_events(events())
    assert engine.replay_to_tick(1).agent_tokens == {"a": 5, "b": 5}
    replayed = engine.replay_to_tick(2)
    assert replayed.agent_tokens == {"a": 3, "b": 7}
    assert replayed.agent_positions["a"] == (1, 0)
    assert replayed.reached_goals["a"] is False  # A truncated plan is not goal arrival.
    assert replayed.remaining_dists["a"] == 0


def test_a_later_keyframe_does_not_apply_an_earlier_transfer_twice():
    stream = events()
    stream.append({"event_type": "KEYFRAME", "tick": 3, "agent_states": {
        "a": {"pos": [2, 0], "tokens": 3, "reached_goal": True},
        "b": {"pos": [3, 1], "tokens": 7, "reached_goal": False}}})
    engine = DeterministicReplayEngine()
    engine.load_events(stream)
    assert engine.max_tick == 3 and engine.get_seek_index() == [1, 3]
    assert engine.replay_to_tick(3).agent_tokens == {"a": 3, "b": 7}
    assert engine.replay_to_tick(4).agent_tokens == {"a": 3, "b": 7}


def test_goal_arrival_uses_recorded_target_even_if_plan_length_is_stale():
    stream = events()
    stream.pop(1)
    engine = DeterministicReplayEngine()
    engine.load_events(stream)
    assert not engine.replay_to_tick(2).reached_goals["a"]
    engine.load_events([{"event_type": "MOVE", "tick": 3, "agent_id": "a",
                         "x": 2, "y": 0, "remaining_dist": 7}])
    assert engine.replay_to_tick(3).reached_goals["a"]


def test_normalized_receipts_apply_in_order_and_preserve_uninvolved_balances():
    from mapf.telemetry.events import AgentMoveEvent, DiagnosticEvent, KeyframeEvent
    from mapf.telemetry.schema import normalize

    records = [
        KeyframeEvent(0, {"a": {"tokens": 5}, "b": {"tokens": 5}, "c": {"tokens": 8}}),
        DiagnosticEvent("TOKEN_TRANSFER", 1, {
            "payer": "a", "payee": "b", "amount": 2,
            "balances_before": {"a": 5, "b": 5}, "balances_after": {"a": 3, "b": 7}}),
        DiagnosticEvent("TOKEN_TRANSFER", 1, {
            "payer": "b", "payee": "c", "amount": 4,
            "balances_before": {"b": 7, "c": 8}, "balances_after": {"b": 3, "c": 12}}),
        AgentMoveEvent(1, "a", 1, 0, False, 1),
    ]
    engine = DeterministicReplayEngine()
    engine.load_events([normalize(record, i + 1) for i, record in enumerate(records)])
    assert engine.replay_to_tick(1).agent_tokens == {"a": 5, "b": 5, "c": 8}
    assert engine.replay_to_tick(2).agent_tokens == {"a": 3, "b": 3, "c": 12}
    assert sum(engine.replay_to_tick(2).agent_tokens.values()) == 18


@pytest.mark.parametrize("compressed", [False, True], ids=["jsonl", "gzip"])
def test_file_replay_handles_blank_lines_and_returns_independent_state(tmp_path, compressed):
    path = tmp_path / ("events.jsonl.gz" if compressed else "events.jsonl")
    raw = "\n\n".join(json.dumps(event) for event in events()) + "\n\n"
    path.write_bytes(gzip.compress(raw.encode()) if compressed else raw.encode())
    engine = DeterministicReplayEngine()
    engine.load_from_file(path)
    state = engine.replay_to_tick(2)
    cloned = state.copy()
    cloned.agent_tokens["a"] = 100
    cloned.agent_positions["a"] = (99, 99)
    cloned.reached_goals["a"] = True
    cloned.remaining_dists["a"] = 100
    cloned.agent_targets["a"] = (99, 99)
    assert state.agent_targets["a"] == (2, 0)
    assert engine.replay_to_tick(2).to_dict() == state.to_dict()
    assert state.to_dict()["state_hash"] != cloned.to_dict()["state_hash"]


@pytest.mark.parametrize(("field", "value"), [
    ("balances_after", {"a": -1, "b": 11}),
    ("balances_after", {"a": 3, "b": 8}),
    ("balances_before", {"a": 4, "b": 6}),
    ("amount", 3),
    ("balances_after", {"a": 3}),
    ("amount", -1),
    ("amount", True),
    ("payer", "missing"),
    ("payee", "missing"),
    ("balances_before", {"a": True, "b": 5}),
], ids=["overdraw", "conservation", "prior-state", "amount", "roster", "negative-amount",
        "boolean-amount", "missing-payer", "missing-payee", "boolean-balance"])
def test_inconsistent_transfer_receipts_do_not_produce_plausible_replay(field, value):
    stream = events()
    stream[1][field] = value
    engine = DeterministicReplayEngine()
    with pytest.raises(ValueError):
        engine.load_events(stream)
        engine.replay_to_tick(2)


def test_conserved_transfer_must_also_match_previously_observed_balance():
    stream = events()
    stream[1].update(balances_before={"a": 4, "b": 6}, balances_after={"a": 2, "b": 8})
    engine = DeterministicReplayEngine()
    engine.load_events(stream)
    with pytest.raises(ValueError, match="prior replay balance"):
        engine.replay_to_tick(2)
