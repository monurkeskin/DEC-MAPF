from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from mapf.core.commitments import CommitmentReservation
from mapf.core.models import (
    AgentState,
    Bid,
    BidDecision,
    Conflict,
    Contract,
    Path,
    Point,
)
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol
from mapf.core.space_time_grid import ReservationTable, SpaceTimeAStar


class BaseAgent(ABC, AgentProtocol):
    """Abstract Base Agent providing common state, movement, and path replanning."""

    def __init__(
        self,
        agent_id: str,
        start_pos: Point,
        target_pos: Point,
        initial_tokens: int = 5,
        commitment_type: Any = None,
    ) -> None:
        from mapf.core.models import CommitmentType

        self._agent_id = agent_id
        self._start_pos = start_pos
        self._current_pos = start_pos
        self._target_pos = target_pos
        self._initial_tokens = initial_tokens
        self._current_tokens = initial_tokens
        self._commitment_type = commitment_type or CommitmentType.STANDARD
        self._commitments: dict[str, CommitmentReservation] = {}
        self._last_conflict_step: int = 0
        self._planned_path: Path = Path(points=[start_pos])
        self._initial_path_length: int = 0
        self._reached_goal: bool = start_pos == target_pos
        self._metadata: dict[str, Any] = {}

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def start_pos(self) -> Point:
        return self._start_pos

    @property
    def current_pos(self) -> Point:
        return self._current_pos

    @property
    def target_pos(self) -> Point:
        return self._target_pos

    @property
    def tokens(self) -> int:
        return self._current_tokens

    @property
    def planned_path(self) -> Path:
        return self._planned_path

    @property
    def reached_goal(self) -> bool:
        return self._reached_goal

    def apply_planned_path(self, new_path: Path) -> None:
        """Atomically apply a validated plan detour."""
        self._planned_path = new_path

    def get_state(self) -> AgentState:
        return AgentState(
            agent_id=self._agent_id,
            current_pos=self._current_pos,
            target_pos=self._target_pos,
            current_tokens=self._current_tokens,
            initial_tokens=self._initial_tokens,
            initial_path_length=self._initial_path_length,
            remaining_path=self._planned_path,
            reached_goal=self._reached_goal,
            metadata=dict(
                self._metadata,
                commitments=[r.to_dict() for r in self._commitments.values()],
            ),
        )

    def plan_initial_path(self, env: EnvironmentProtocol) -> Path:
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

    def step(self, current_time: int) -> Point:
        """Advance one step along planned path and prune past commitments."""
        if self._current_pos == self._target_pos:
            self._reached_goal = True

        if len(self._planned_path.points) > 1:
            # Advance to next point
            self._planned_path = Path(points=self._planned_path.points[1:])
            self._current_pos = self._planned_path.points[0]
        elif len(self._planned_path.points) == 1:
            self._current_pos = self._planned_path.points[0]

        if self._current_pos == self._target_pos:
            self._reached_goal = True

        self._prune_commitments(current_time + 1)
        return self._current_pos

    def force_move(
        self, new_pos: Point, env: EnvironmentProtocol, current_time: int
    ) -> Point:
        """Apply an evasive or held movement, pruning commitments and replanning to target."""
        self._current_pos = new_pos
        self._prune_commitments(current_time + 1)
        if self._current_pos == self._target_pos:
            self._reached_goal = True
            self._planned_path = Path(points=[self._current_pos])
            return self._current_pos

        # Replan from new position toward target
        fov_size = getattr(self, "fov_size", env.config.fov_size)
        local_obs = env.config.obstacles | env.get_fov_obstacles(
            self._current_pos, fov_size
        )
        planner = SpaceTimeAStar(
            grid_width=env.config.grid_width,
            grid_height=env.config.grid_height,
            obstacles=local_obs,
        )
        res_table = ReservationTable()
        self.reserve_commitments(res_table, current_time + 1)

        new_path = planner.search(
            start=self._current_pos,
            goal=self._target_pos,
            start_time=current_time + 1,
            reservation_table=res_table,
            allow_wait=env.config.setting.allow_wait,
            max_expansions=env.config.max_astar_expansions,
            max_time_steps=max(0, env.config.max_steps - (current_time + 1)),
            permanent_at_goal=not env.config.setting.disappear_at_target,
        )
        if new_path is not None:
            self._planned_path = new_path
        else:
            self._planned_path = Path(points=[self._current_pos])

        return self._current_pos

    def adjust_tokens(self, delta: int) -> None:
        if self._current_tokens + delta < 0:
            raise ValueError("Token overdraft")
        self._current_tokens += delta

    def on_contract_agreed(self, contract: Contract, current_time: int) -> None:
        """Apply newly agreed path, token adjustments, and commitment rules (SC/DC/ZC)."""
        from mapf.core.models import CommitmentType

        if contract.agent_a == self._agent_id:
            if contract.token_transfer > self._current_tokens:
                raise ValueError("Token overdraft")
            my_path = contract.path_a
            opp_path = contract.path_b
            self._planned_path = my_path
            self.adjust_tokens(-contract.token_transfer)
        elif contract.agent_b == self._agent_id:
            if -contract.token_transfer > self._current_tokens:
                raise ValueError("Token overdraft")
            my_path = contract.path_b
            opp_path = contract.path_a
            self._planned_path = my_path
            self.adjust_tokens(contract.token_transfer)
        else:
            return

        if contract.accepted_by is None or contract.accepted_by == self._agent_id:
            points = (contract.allocated_path or opp_path).points
            if self._commitment_type == CommitmentType.DYNAMIC:
                horizon = (contract.conflict_tick - current_time
                           if contract.conflict_tick is not None else self._last_conflict_step)
                points = points[: max(0, horizon) + 1]
            opponent = (
                contract.agent_b
                if contract.agent_a == self._agent_id
                else contract.agent_a
            )
            self._commitments[contract.session_id] = CommitmentReservation(
                contract.session_id,
                self._agent_id,
                opponent,
                current_time,
                tuple(points),
                self._commitment_type.value,
            )

    def _prune_commitments(self, current_tick: int) -> None:
        self._commitments = {
            key: record for key, record in self._commitments.items()
            if record.is_active(current_tick)
        }

    def respects_commitments(self, path: Path, current_tick: int, *, stay_at_goal: bool) -> bool:
        return not any(record.conflicts_with(path, current_tick, stay_at_goal=stay_at_goal)
                       for record in self._commitments.values())

    def reserve_commitments(self, table: ReservationTable, current_tick: int) -> None:
        """Retain every counterparty's vertex and edge constraints at the same tick."""
        for record in self._commitments.values():
            record.add_to(table, current_tick)

    def propose_response(self, bid: Bid, env: EnvironmentProtocol, current_time: int) -> BidDecision:
        """Pure public bridge for legacy strategy callbacks that propose by mutation."""
        from mapf.negotiation.ledger import restore_agent, snapshot_agent
        before = snapshot_agent(self)
        try:
            accepted = self.evaluate_bid(bid, env, current_time)
            components = dict(getattr(self, "_last_decision", {}))
            return BidDecision(accepted=accepted, proposed_path=self.planned_path,
                               reason=str(components.get("reason", "ACCEPT" if accepted else "REJECT")),
                               components=components)
        finally:
            restore_agent(self, before)

    @abstractmethod
    def on_pre_negotiation(
        self,
        opponent_id: str,
        conflict: Conflict,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> None: ...

    @abstractmethod
    def make_bid(
        self,
        opponent_id: str,
        last_opponent_bid: Bid | None,
        env: EnvironmentProtocol,
        current_time: int,
        round_num: int,
    ) -> Bid: ...

    @abstractmethod
    def evaluate_bid(
        self,
        bid: Bid,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> bool: ...


def goal_reached(agent: AgentProtocol) -> bool:
    """Read the built-in flag without constructing a full public state snapshot.

    Custom state/property overrides and structural legacy agents retain get_state
    semantics. This is a read optimization, not a new agent-interface requirement.
    """
    if (isinstance(agent, BaseAgent) and type(agent).get_state is BaseAgent.get_state
            and getattr(type(agent), "reached_goal", None) is BaseAgent.reached_goal):
        return agent.reached_goal
    return agent.get_state().reached_goal
