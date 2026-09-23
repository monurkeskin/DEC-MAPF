from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import Any

from mapf.agents.base import BaseAgent
from mapf.core.heat import DecisionHeatValues
from mapf.core.models import (
    Bid,
    Conflict,
    Path,
    Point,
    SimulationConfig,
)
from mapf.core.protocols import EnvironmentProtocol
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar


class HeatWeights(Mapping[Point, float]):
    """Owned immutable field shared safely by speculative transaction snapshots.

    The constructor detaches caller data. Only immutable Point/float values enter
    the private read-only mapping; strategy extension dictionaries still deep-copy.
    """

    __slots__ = ("_values",)
    _values: Mapping[Point, float]

    def __init__(self, values: Mapping[Point, float]) -> None:
        object.__setattr__(
            self,
            "_values",
            MappingProxyType(
                {
                    Point(point.x, point.y): float(value)
                    for point, value in values.items()
                }
            ),
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("Heat fields are immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("Heat fields are immutable")

    def __getitem__(self, key: Point) -> float:
        return self._values[key]

    def __iter__(self) -> Iterator[Point]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __deepcopy__(self, memo: dict[int, Any]) -> HeatWeights:
        if type(self) is not HeatWeights:
            raise TypeError(
                "A HeatWeights subclass must define its own snapshot semantics"
            )
        return self


class HeatMapAgent(BaseAgent):
    """Rank candidate paths using local, time-indexed congestion estimates."""

    def __init__(
        self,
        agent_id: str,
        start_pos: Point,
        target_pos: Point,
        initial_tokens: int = 5,
        fov_size: int = 5,
        commitment_type: Any = None,
    ) -> None:
        super().__init__(
            agent_id,
            start_pos,
            target_pos,
            initial_tokens,
            commitment_type=commitment_type,
        )
        self.fov_size = fov_size
        self._active_conflict: Conflict | None = None
        self._cell_weights: Mapping[Point, float] = HeatWeights({})
        self._time_weights: tuple[Mapping[Point, float], ...] = ()
        self._opponent_id: str | None = None
        self._weights_cache: tuple[Any, HeatWeights, tuple[HeatWeights, ...]] | None = (
            None
        )

    def _compute_heatmap_weights(
        self, env: EnvironmentProtocol
    ) -> Mapping[Point, float]:
        """Keep one field per relative tick and omit the bilateral opponent.

        The finite Manhattan kernel is the documented modern kernel. Java also
        uses agent-center weight 1; its CAP=999 is an obstacle penalty.
        """
        broadcasts = env.get_fov_broadcasts(
            center=self._current_pos,
            fov_size=self.fov_size,
            requesting_agent_id=self._agent_id,
        )

        cache_key = self._heat_cache_key(broadcasts, env.config)
        if self._weights_cache is not None and self._weights_cache[0] == cache_key:
            self._time_weights = self._weights_cache[2]
            return self._weights_cache[1]
        weights, fields = self._build_heat_fields(broadcasts, env.config)
        self._time_weights = fields
        self._weights_cache = (cache_key, weights, fields)
        return weights

    def _heat_cache_key(
        self, broadcasts: dict[str, Path], config: SimulationConfig
    ) -> tuple[Any, ...]:
        return (
            self._current_pos,
            self._opponent_id,
            self.fov_size,
            config.grid_width,
            config.grid_height,
            config.broadcast_horizon,
            config.negotiation_horizon,
            tuple(
                (oid, tuple(path.points)) for oid, path in sorted(broadcasts.items())
            ),
        )

    def _build_heat_fields(
        self, broadcasts: dict[str, Path], config: SimulationConfig
    ) -> tuple[HeatWeights, tuple[HeatWeights, ...]]:
        horizon = config.broadcast_horizon or self.fov_size
        weights: dict[Point, float] = {}
        fields: list[dict[Point, float]] = [{} for _ in range(horizon)]
        for other_id, other_path in broadcasts.items():
            if other_id in (self._agent_id, self._opponent_id):
                continue
            for relative_tick, center in enumerate(other_path.points[:horizon]):
                field = fields[relative_tick]
                for point, value in _kernel(center, self.fov_size // 2, config):
                    weights[point] = weights.get(point, 0.0) + value
                    field[point] = field.get(point, 0.0) + value
        return HeatWeights(weights), tuple(HeatWeights(field) for field in fields)

    def plan_initial_path(self, env: EnvironmentProtocol) -> Path:
        """Plan a shortest baseline route without congestion weights."""
        planner = SpaceTimeAStar(
            grid_width=env.config.grid_width,
            grid_height=env.config.grid_height,
            obstacles=env.config.obstacles,
        )
        path = planner.search(
            start=self._current_pos,
            goal=self._target_pos,
            start_time=0,
            allow_wait=env.config.setting.allow_wait,
            max_expansions=env.config.max_astar_expansions,
            max_time_steps=max(0, env.config.max_steps - (0)),
            permanent_at_goal=not env.config.setting.disappear_at_target,
        )
        if path is None:
            path = Path(points=[self._current_pos])

        self._planned_path = path
        self._initial_path_length = path.length
        return path

    def on_pre_negotiation(
        self,
        opponent_id: str,
        conflict: Conflict,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> None:
        self._active_conflict = conflict
        self._last_conflict_step = max(0, conflict.end_time - current_time)
        self._opponent_id = opponent_id
        self._cell_weights = self._compute_heatmap_weights(env)

    def decision_heat_values(self) -> DecisionHeatValues:
        """Expose exactly the immutable fields used by this negotiation decision."""
        return DecisionHeatValues(
            self._current_pos,
            self._opponent_id,
            self.fov_size,
            self._cell_weights,
            self._time_weights,
        )

    def _estimate_path_heat(self, path: Path) -> float:
        """Modern action cost plus time-aligned observable congestion."""
        weight = float(len(path.points) - 1)
        for tick, pt in enumerate(path.points):
            if tick < len(self._time_weights):
                weight += self._time_weights[tick].get(pt, 0.0)
        return weight

    def _rank_candidates(self, candidates: list[Path]) -> list[tuple[Path, float]]:
        """Rank by normalized path-plus-congestion cost and explicit length tie break."""
        if not candidates:
            return []

        weights = [self._estimate_path_heat(p) for p in candidates]
        lengths = [float(len(p.points) - 1) for p in candidates]

        min_w, max_w = min(weights), max(weights)
        min_l, max_l = min(lengths), max(lengths)

        ranked: list[tuple[Path, float]] = []
        for p, w, l in zip(candidates, weights, lengths):
            u_heat = _normalized_heat(w, min_w, max_w)
            offset = _length_offset(l, min_l, max_l)
            ranked.append((p, u_heat - offset))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked

    def make_bid(
        self,
        opponent_id: str,
        last_opponent_bid: Bid | None,
        env: EnvironmentProtocol,
        current_time: int,
        round_num: int,
    ) -> Bid:
        usage = getattr(self, "_acknowledged_usage", round_num)
        rate = self._calculate_concession_rate(token_cost=usage)
        if rate >= 1.0 and self._current_tokens >= usage:
            # GREEDY: Insist on current planned path (matching Java run_greedy GetOwnBroadcastPath)
            return Bid(
                bidder_id=self._agent_id,
                proposed_path=self._planned_path,
                token_offered=min(self._current_tokens, round_num),
                round_num=round_num,
            )

        reservations = self._response_reservations(
            opponent_id, last_opponent_bid, current_time
        )
        candidates = self._response_candidates(reservations, env, current_time)
        ranked = self._rank_candidates(candidates)
        chosen_path = ranked[0][0] if ranked else self._planned_path
        return Bid(
            bidder_id=self._agent_id,
            proposed_path=chosen_path,
            token_offered=0,
            round_num=round_num,
        )

    def evaluate_bid(
        self,
        bid: Bid,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> bool:
        reservations = self._response_reservations(bid.bidder_id, bid, current_time)
        candidates = self._response_candidates(reservations, env, current_time)

        if not candidates:
            self._last_decision = {"reason": "NO_FEASIBLE_RESPONSE", "feasible": False}
            return False

        ranked = self._rank_candidates(candidates)
        alternative_path = ranked[0][0]

        reference = getattr(self, "_negotiation_reference_path", self._planned_path)
        delay = alternative_path.length - reference.length
        self._last_decision = {
            "candidate_actions": alternative_path.length,
            "reference_actions": reference.length,
            "path_heat": self._estimate_path_heat(alternative_path)
            - alternative_path.length,
            "score": ranked[0][1],
            "candidate_rank": 1,
            "candidate_count": len(candidates),
            "delay": delay,
            "concession_rate": self._calculate_concession_rate(0),
            "feasible": True,
            "reason": "NON_WORSENING_RESPONSE" if delay <= 0 else "LONGER_RESPONSE",
        }
        return self._accept_response(
            alternative_path, bid, env.config.negotiation_protocol
        )

    def _response_reservations(
        self, opponent_id: str, bid: Bid | None, current_time: int
    ) -> ReservationTable:
        res_table = ReservationTable()
        if bid is not None:
            res_table.reserve_path(
                agent_id=opponent_id, path=bid.proposed_path, start_time=current_time
            )

        self.reserve_commitments(res_table, current_time)
        return res_table

    def _response_candidates(
        self, res_table: ReservationTable, env: EnvironmentProtocol, current_time: int
    ) -> list[Path]:
        local_obs = env.config.obstacles | env.get_fov_obstacles(
            self._current_pos, self.fov_size
        )
        planner = SpaceTimeAStar(
            grid_width=env.config.grid_width,
            grid_height=env.config.grid_height,
            obstacles=local_obs,
            candidate_cache=getattr(env, "candidate_cache", None),
        )

        return planner.find_bounded_candidate_paths(
            start=self._current_pos,
            goal=self._target_pos,
            start_time=current_time,
            reservation_table=res_table,
            allow_wait=env.config.setting.allow_wait,
            max_extra_steps=1,
            max_candidates=8,
            cell_weights=self._cell_weights,
            tie_break_weights=True,
            max_expansions=env.config.max_astar_expansions,
            max_time_steps=max(0, env.config.max_steps - (current_time)),
            permanent_at_goal=not env.config.setting.disappear_at_target,
        )


def _kernel(
    center: Point, radius: int, config: SimulationConfig
) -> Iterator[tuple[Point, float]]:
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            distance = abs(dx) + abs(dy)
            if distance > radius:
                continue
            x, y = center.x + dx, center.y + dy
            if 0 <= x < config.grid_width and 0 <= y < config.grid_height:
                yield (
                    Point(x, y),
                    max(0.0, float(radius + 1 - distance) / float(radius + 1)),
                )


def _normalized_heat(weight: float, lower: float, upper: float) -> float:
    return 1.0 - ((weight - lower) / (upper - lower)) if upper > lower else 1.0


def _length_offset(length: float, lower: float, upper: float) -> float:
    return (1.0 - ((upper - length) / (upper - lower))) * 1e-6 if upper > lower else 0.0
