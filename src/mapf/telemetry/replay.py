"""Deterministic Telemetry Replay and State Reducer Engine (L07, L08).

Reconstructs exact discrete simulation states at any tick by applying
typed event reducers to initial manifests and periodic keyframe snapshots.
Provides seek indexing for instant random-access replay.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


class ReplayState:
    """Reconstructed simulation state at a discrete tick."""

    __slots__ = ("agent_positions", "agent_tokens", "reached_goals", "remaining_dists", "tick")

    def __init__(self, tick: int = 0) -> None:
        self.tick = tick
        self.agent_positions: dict[str, tuple[int, int]] = {}
        self.agent_tokens: dict[str, int] = {}
        self.reached_goals: dict[str, bool] = {}
        self.remaining_dists: dict[str, int] = {}

    def copy(self) -> ReplayState:
        s = ReplayState(self.tick)
        s.agent_positions = dict(self.agent_positions)
        s.agent_tokens = dict(self.agent_tokens)
        s.reached_goals = dict(self.reached_goals)
        s.remaining_dists = dict(self.remaining_dists)
        return s

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
        """List of tick indices that have full keyframe snapshots for instant seeking."""
        return sorted(self._keyframes.keys())

    def replay_to_tick(self, target_tick: int) -> ReplayState:
        """Reconstruct state at target_tick by seeking to the nearest prior keyframe and advancing."""
        target_tick = max(target_tick, 0)

        # Find nearest keyframe <= target_tick
        candidates = [t for t in self._keyframes if t <= target_tick]
        base_tick = max(candidates) if candidates else 0

        state = ReplayState(tick=base_tick)
        if base_tick in self._keyframes:
            kf = self._keyframes[base_tick]
            for aid, sdata in kf.items():
                pos = sdata.get("pos", [0, 0])
                state.agent_positions[aid] = (pos[0], pos[1])
                state.agent_tokens[aid] = sdata.get("tokens", 5)
                state.reached_goals[aid] = sdata.get("reached_goal", False)
                state.remaining_dists[aid] = sdata.get("remaining_dist", 0)

        # Apply moves from base_tick + 1 up to target_tick
        for t in range(base_tick + 1, target_tick + 1):
            state.tick = t
            moves = self._moves_by_tick.get(t, [])
            for m in moves:
                aid = m["agent_id"]
                state.agent_positions[aid] = (m["x"], m["y"])
                rem = m.get("remaining_dist", 0)
                state.remaining_dists[aid] = rem
                if rem == 0:
                    state.reached_goals[aid] = True

        return state
