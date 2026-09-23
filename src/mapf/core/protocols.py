from __future__ import annotations

from typing import Protocol, runtime_checkable

from mapf.core.models import (
    AgentState,
    Bid,
    Conflict,
    Contract,
    Path,
    Point,
    SimulationConfig,
)


@runtime_checkable
class EnvironmentProtocol(Protocol):
    """World query interface available to agents within their Field of View (FoV)."""

    @property
    def config(self) -> SimulationConfig: ...

    def is_obstacle(self, p: Point) -> bool: ...

    def is_within_bounds(self, p: Point) -> bool: ...

    def get_fov_obstacles(self, center: Point, fov_size: int) -> set[Point]: ...

    def get_fov_broadcasts(
        self, center: Point, fov_size: int, requesting_agent_id: str
    ) -> dict[str, Path]: ...


@runtime_checkable
class AgentProtocol(Protocol):
    """Contract for any decentralized MAPF agent strategy."""

    @property
    def agent_id(self) -> str: ...

    @property
    def start_pos(self) -> Point: ...

    @property
    def current_pos(self) -> Point: ...

    @property
    def target_pos(self) -> Point: ...

    @property
    def tokens(self) -> int: ...

    @property
    def planned_path(self) -> Path: ...

    def get_state(self) -> AgentState: ...

    def plan_initial_path(self, env: EnvironmentProtocol) -> Path: ...

    def apply_planned_path(self, new_path: Path) -> None: ...

    def step(self, current_time: int) -> Point: ...

    def force_move(
        self, new_pos: Point, env: EnvironmentProtocol, current_time: int
    ) -> Point: ...

    def on_pre_negotiation(
        self,
        opponent_id: str,
        conflict: Conflict,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> None: ...

    def make_bid(
        self,
        opponent_id: str,
        last_opponent_bid: Bid | None,
        env: EnvironmentProtocol,
        current_time: int,
        round_num: int,
    ) -> Bid: ...

    def evaluate_bid(
        self,
        bid: Bid,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> bool: ...

    def on_contract_agreed(self, contract: Contract, current_time: int) -> None: ...


@runtime_checkable
class NegotiatorProtocol(Protocol):
    """Manages bilateral negotiation sessions between conflicting agents."""

    def negotiate(
        self,
        agent_a: AgentProtocol,
        agent_b: AgentProtocol,
        conflict: Conflict,
        env: EnvironmentProtocol,
        current_time: int,
    ) -> Contract | None: ...
