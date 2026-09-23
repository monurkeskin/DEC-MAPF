"""Reconstruct recorded agent state using indexed events and replay keyframes.

Seeking starts at the nearest preceding keyframe and applies later events.
The result supports visual replay, not exact resumption of a solver.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from mapf.telemetry._transfers import apply_transfer


class ReplayState:
    """Reconstructed simulation state at a discrete tick."""

    __slots__ = ("agent_positions", "agent_targets", "agent_tokens", "reached_goals", "remaining_dists", "tick")

    def __init__(self, tick: int = 0) -> None:
        self.tick = tick
        self.agent_positions: dict[str, tuple[int, int]] = {}
        self.agent_targets: dict[str, tuple[int, int]] = {}
        self.agent_tokens: dict[str, int] = {}
        self.reached_goals: dict[str, bool] = {}
        self.remaining_dists: dict[str, int] = {}

    def copy(self) -> ReplayState:
        s = ReplayState(self.tick)
        s.agent_positions = dict(self.agent_positions)
        s.agent_targets = dict(self.agent_targets)
        s.agent_tokens = dict(self.agent_tokens)
        s.reached_goals = dict(self.reached_goals)
        s.remaining_dists = dict(self.remaining_dists)
        return s

    def restore_keyframe(self, agents: dict[str, dict[str, Any]]) -> None:
        for aid, recorded in agents.items():
            position = recorded.get("pos", [0, 0])
            self.agent_positions[aid] = (position[0], position[1])
            self.agent_tokens[aid] = recorded.get("tokens", 5)
            self.reached_goals[aid] = recorded.get("reached_goal", False)
            self.remaining_dists[aid] = recorded.get("remaining_dist", 0)
            if "target" in recorded:
                self.agent_targets[aid] = tuple(recorded["target"])

    def apply_move(self, move: dict[str, Any]) -> None:
        aid = move["agent_id"]
        position = (move["x"], move["y"])
        self.agent_positions[aid] = position
        remaining = move.get("remaining_dist", 0)
        self.remaining_dists[aid] = remaining
        if aid in self.agent_targets:
            self.reached_goals[aid] = position == self.agent_targets[aid]
        elif remaining == 0:
            # Unversioned historical snapshots may lack goals. Retain their legacy
            # distance inference, while current target-bearing snapshots use coordinates.
            self.reached_goals[aid] = True

    def compute_hash(self) -> str:
        """Deterministic SHA256 digest of the reconstructed state."""
        canonical = {
            "tick": self.tick,
            "positions": sorted((aid, pos) for aid, pos in self.agent_positions.items()),
            "tokens": sorted(self.agent_tokens.items()),
            "reached": sorted(self.reached_goals.items()),
        }
        raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "agent_positions": self.agent_positions,
            "agent_tokens": self.agent_tokens,
            "reached_goals": self.reached_goals,
            "state_hash": self.compute_hash(),
        }


class DeterministicReplayEngine:
    """Event reducer that processes discrete telemetry streams with seek index support."""

    def __init__(self) -> None:
        self._manifest: dict[str, Any] | None = None
        self._keyframes: dict[int, dict[str, Any]] = {}
        self._moves_by_tick: dict[int, list[dict[str, Any]]] = {}
        self._transfers_by_tick: dict[int, list[dict[str, Any]]] = {}
        self._max_tick = 0

    @property
    def max_tick(self) -> int:
        return self._max_tick

    def load_events(self, events: list[dict[str, Any]]) -> None:
        """Ingest raw event records into internal indexed structures."""
        for ev in events:
            ev_type = ev.get("event_type")
            if ev_type == "MANIFEST":
                self._manifest = ev
            elif ev_type == "KEYFRAME":
                tick = ev["tick"]
                self._keyframes[tick] = ev.get("agent_states", {})
                self._max_tick = max(self._max_tick, tick)
            elif ev_type == "MOVE":
                tick = ev["tick"]
                self._moves_by_tick.setdefault(tick, []).append(ev)
                self._max_tick = max(self._max_tick, tick)
            elif ev_type == "TOKEN_TRANSFER":
                # A decision at pre-move t belongs to the following post-move frame.
                tick = ev["tick"] + int(ev.get("phase") == "pre_move")
                self._transfers_by_tick.setdefault(tick, []).append(ev)

    def load_from_file(self, file_path: Path | str) -> None:
        """Read and index events from a .jsonl or .jsonl.gz file."""
        p = Path(file_path)
        events: list[dict[str, Any]] = []
        if p.suffix == ".gz":
            with gzip.open(p, "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
        else:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
        self.load_events(events)

    def get_seek_index(self) -> list[int]:
        """List recorded keyframe ticks available as seek starting points."""
        return sorted(self._keyframes.keys())

    def replay_to_tick(self, target_tick: int) -> ReplayState:
        """Reconstruct state at target_tick by seeking to the nearest prior keyframe and advancing."""
        target_tick = max(target_tick, 0)

        # Find nearest keyframe <= target_tick
        candidates = [t for t in self._keyframes if t <= target_tick]
        base_tick = max(candidates) if candidates else 0

        state = ReplayState(tick=base_tick)
        if base_tick in self._keyframes:
            state.restore_keyframe(self._keyframes[base_tick])

        # Apply moves from base_tick + 1 up to target_tick
        for t in range(base_tick + 1, target_tick + 1):
            state.tick = t
            for event in self._transfers_by_tick.get(t, []):
                state.agent_tokens = apply_transfer(state.agent_tokens, event)
            for move in self._moves_by_tick.get(t, []):
                state.apply_move(move)

        return state
