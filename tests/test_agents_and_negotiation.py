from mapf.agents.greedy import ConcederAgent
from mapf.agents.heatmap import HeatMapAgent
from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import (
    Path,
    Point,
    SimulationConfig,
    SimulationSetting,
)
from mapf.core.protocols import EnvironmentProtocol
from mapf.negotiation.conflict import detect_conflicts
from mapf.negotiation.session import BilateralNegotiationSession


class MockEnvironment(EnvironmentProtocol):
    def __init__(self, config: SimulationConfig) -> None:
        self._config = config

    @property
    def config(self) -> SimulationConfig:
        return self._config

    def is_obstacle(self, p: Point) -> bool:
        return p in self._config.obstacles

    def is_within_bounds(self, p: Point) -> bool:
        return (
            0 <= p.x < self._config.grid_width and 0 <= p.y < self._config.grid_height
        )

    def get_fov_obstacles(self, center: Point, fov_size: int) -> set[Point]:
        radius = fov_size // 2
        return {
            obs
            for obs in self._config.obstacles
            if abs(obs.x - center.x) <= radius and abs(obs.y - center.y) <= radius
        }

    def get_fov_broadcasts(
        self, center: Point, fov_size: int, requesting_agent_id: str
    ) -> dict[str, Path]:
        return {}


def test_path_aware_agent_initial_planning():
    config = SimulationConfig(grid_width=10, grid_height=10)
    env = MockEnvironment(config)

    agent = PathAwareAgent(
        agent_id="Agent_1",
        start_pos=Point(x=0, y=0),
        target_pos=Point(x=4, y=4),
        initial_tokens=5,
    )
    path = agent.plan_initial_path(env)
    assert path.length == 8  # 4 + 4 action steps (transitions)
    assert len(path.points) == 9  # 9 points total
    assert path.points[0] == Point(x=0, y=0)
    assert path.points[-1] == Point(x=4, y=4)


def test_heatmap_agent_fov_weights():
    obstacles = {Point(x=2, y=2)}
    config = SimulationConfig(
        grid_width=10, grid_height=10, obstacles=obstacles, fov_size=5
    )
    env = MockEnvironment(config)

    agent = HeatMapAgent(
        agent_id="Agent_HM",
        start_pos=Point(x=1, y=2),
        target_pos=Point(x=4, y=2),
        initial_tokens=5,
    )
    path = agent.plan_initial_path(env)
    assert path is not None
    assert Point(x=2, y=2) not in path.points  # Detoured around obstacle


def test_bilateral_negotiation_success():
    """Agent 1 and Agent 2 have a head-on collision at (2,0) at t=2."""
    config = SimulationConfig(
        grid_width=10,
        grid_height=10,
        setting=SimulationSetting.SETTING_4,
    )
    env = MockEnvironment(config)

    # Head-on conflict setup
    agent_1 = PathAwareAgent("A1", Point(x=0, y=0), Point(x=4, y=0), initial_tokens=5)
    agent_2 = ConcederAgent("A2", Point(x=4, y=0), Point(x=0, y=0), initial_tokens=5)

    agent_1.plan_initial_path(env)
    agent_2.plan_initial_path(env)

    # Detect initial conflict
    conflicts = detect_conflicts(
        {"A1": agent_1.planned_path, "A2": agent_2.planned_path}
    )
    assert len(conflicts) > 0
    conflict = conflicts[0]

    session = BilateralNegotiationSession(max_rounds=6)
    contract = session.negotiate(agent_1, agent_2, conflict, env, current_time=0)

    assert contract is not None
    # Check the agreed paths independently of the negotiation outcome.
    agreed_conflicts = detect_conflicts(
        {"A1": agent_1.planned_path, "A2": agent_2.planned_path}
    )
    assert len(agreed_conflicts) == 0
