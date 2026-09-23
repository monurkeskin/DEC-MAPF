"""Recipient-owned knowledge of permanent obstacles learned through observation."""

from dataclasses import replace

from mapf.core.models import Point, SimulationConfig
from mapf.core.observations import Observation
from mapf.core.protocols import EnvironmentProtocol


class ObstacleMemory:
    """Retain delivered parked cells for one world, without querying other agents.

    Observation.obstacles contains static cells and currently visible parked
    cells, never moving agents. Only the latter need memory beyond the static map.
    """

    def __init__(self) -> None:
        self._known: dict[str, frozenset[Point]] = {}

    def apply(self, observation: Observation, config: SimulationConfig) -> Observation:
        if config.setting.disappear_at_target:
            self._known.clear()
            return observation
        learned = observation.obstacles - config.obstacles - {observation.position}
        known = self._known.get(observation.agent_id, frozenset()) | learned
        self._known[observation.agent_id] = known
        if observation.remembered_obstacles == known:
            return observation
        return replace(observation, remembered_obstacles=known)


def planning_obstacles(
    env: EnvironmentProtocol, position: Point, fov_size: int
) -> set[Point]:
    """Combine static geometry, current visibility and the recipient's memory.

    Custom environments without the optional remembered_obstacles property retain
    their existing static-plus-FoV semantics. Strategy views supplied by the world
    always expose an immutable recipient-local memory.
    """
    return (
        env.config.obstacles
        | env.get_fov_obstacles(position, fov_size)
        | getattr(env, "remembered_obstacles", frozenset())
    )
