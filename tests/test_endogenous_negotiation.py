from mapf.core.models import (
    Bid,
    Conflict,
    ConflictType,
    Path,
    Point,
    SimulationConfig,
    SimulationSetting,
)
from mapf.core.protocols import AgentProtocol, EnvironmentProtocol
from mapf.negotiation.session import BilateralNegotiationSession


class MockEnv(EnvironmentProtocol):
    def __init__(self, config: SimulationConfig) -> None:
        self._config = config

    @property
    def config(self) -> SimulationConfig:
        return self._config

    def is_obstacle(self, p: Point) -> bool:
        return False

    def is_within_bounds(self, p: Point) -> bool:
        return 0 <= p.x < self._config.grid_width and 0 <= p.y < self._config.grid_height

    def get_fov_obstacles(self, center: Point, fov_size: int) -> set[Point]:
        return set()

    def get_fov_broadcasts(self, center: Point, fov_size: int, requesting_agent_id: str) -> dict[str, Path]:
        return {}


class StubbornAgent(AgentProtocol):
    """An agent that repeatedly proposes the same path without escalating tokens."""

    def __init__(self, agent_id: str, fixed_path: Path) -> None:
        self._agent_id = agent_id
        self._planned_path = fixed_path
        self.bids_made: list[Bid] = []
        self.evaluate_calls: int = 0

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def current_pos(self) -> Point:
        return self._planned_path.points[0]

    @property
    def target_pos(self) -> Point:
        return self._planned_path.points[-1]

    @property
    def current_tokens(self) -> int:
        return 5

    @property
    def planned_path(self) -> Path:
        return self._planned_path

    @planned_path.setter
    def planned_path(self, p: Path) -> None:
        self._planned_path = p

    def plan_initial_path(self, env: EnvironmentProtocol) -> Path:
        return self._planned_path

    def on_pre_negotiation(self, opponent_id: str, conflict: Conflict, env: EnvironmentProtocol, current_time: int) -> None:
        pass

    def make_bid(self, opponent_id: str, last_opponent_bid: Bid | None, env: EnvironmentProtocol, current_time: int, round_num: int) -> Bid:
        bid = Bid(
            bidder_id=self._agent_id,
            proposed_path=self._planned_path,
            token_offered=0,  # Zero concession: identical path, zero token escalation
            round_num=round_num,
        )
        self.bids_made.append(bid)
        return bid

    def evaluate_bid(self, bid: Bid, env: EnvironmentProtocol, current_time: int) -> bool:
        self.evaluate_calls += 1
        return False  # Stubbornly reject

    def on_contract_agreed(self, contract: object, current_time: int) -> None:
        pass


class EscalatingAgent(AgentProtocol):
    """An agent that escalates token offers up to round 7 before opponent accepts."""

    def __init__(self, agent_id: str, path: Path, accept_at_token: int = 4) -> None:
        self._agent_id = agent_id
        self._planned_path = path
        self.accept_at_token = accept_at_token
        self.token_offer = 0

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def current_pos(self) -> Point:
        return self._planned_path.points[0]

    @property
    def target_pos(self) -> Point:
        return self._planned_path.points[-1]

    @property
    def current_tokens(self) -> int:
        return 10

    @property
    def planned_path(self) -> Path:
        return self._planned_path

    @planned_path.setter
    def planned_path(self, p: Path) -> None:
        self._planned_path = p

    def plan_initial_path(self, env: EnvironmentProtocol) -> Path:
        return self._planned_path

    def on_pre_negotiation(self, opponent_id: str, conflict: Conflict, env: EnvironmentProtocol, current_time: int) -> None:
        pass

    def make_bid(self, opponent_id: str, last_opponent_bid: Bid | None, env: EnvironmentProtocol, current_time: int, round_num: int) -> Bid:
        self.token_offer += 1
        return Bid(
            bidder_id=self._agent_id,
            proposed_path=self._planned_path,
            token_offered=self.token_offer,
            round_num=round_num,
        )

    def evaluate_bid(self, bid: Bid, env: EnvironmentProtocol, current_time: int) -> bool:
        # Accepts only if offered token meets threshold
        return bid.token_offered >= self.accept_at_token

    def on_contract_agreed(self, contract: object, current_time: int) -> None:
        pass


def test_endogenous_impasse_detection():
    """Two stubborn agents that both make zero concessions must reach stationary impasse naturally."""
    config = SimulationConfig(grid_width=10, grid_height=10, setting=SimulationSetting.SETTING_4)
    env = MockEnv(config)

    path_a = Path(points=[Point(x=0, y=0), Point(x=1, y=0), Point(x=2, y=0)])
    path_b = Path(points=[Point(x=2, y=0), Point(x=1, y=0), Point(x=0, y=0)])

    agent_a = StubbornAgent("A", path_a)
    agent_b = StubbornAgent("B", path_b)

    conflict = Conflict(
        agent_a="A",
        agent_b="B",
        conflict_type=ConflictType.VERTEX,
        location_a=Point(x=1, y=0),
        time=1,
    )

    session = BilateralNegotiationSession(max_rounds=30)
    contract = session.negotiate(agent_a, agent_b, conflict, env, current_time=0)

    # Must terminate with impasse (None)
    assert contract is None
    # Must NOT run until round 30! It must detect fixed-point impasse by round 3 or 4!
    total_bids = len(agent_a.bids_made) + len(agent_b.bids_made)
    assert total_bids <= 4, f"Expected impasse within 4 rounds, but took {total_bids} rounds"


def test_multiround_bargaining_without_premature_truncation():
    """Bargaining requiring > 5 rounds must succeed now that arbitrary 5-round cap is removed."""
    config = SimulationConfig(grid_width=10, grid_height=10, setting=SimulationSetting.SETTING_4)
    env = MockEnv(config)

    path_a = Path(points=[Point(x=0, y=0), Point(x=1, y=0), Point(x=2, y=0)])
    # Non-conflicting alternative path for B
    path_b = Path(points=[Point(x=0, y=2), Point(x=1, y=2), Point(x=2, y=2)])

    agent_a = EscalatingAgent("A", path_a, accept_at_token=100)
    agent_b = EscalatingAgent("B", path_b, accept_at_token=4)

    conflict = Conflict(
        agent_a="A",
        agent_b="B",
        conflict_type=ConflictType.VERTEX,
        location_a=Point(x=1, y=0),
        time=1,
    )

    session = BilateralNegotiationSession(max_rounds=30)
    contract = session.negotiate(agent_a, agent_b, conflict, env, current_time=0)

    # Must successfully reach agreement once token reaches 4 (at round 7)
    assert contract is not None
    assert contract.token_transfer == 4
