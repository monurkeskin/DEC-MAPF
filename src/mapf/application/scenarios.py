"""Scenario repository, MovingAI parser, and semantic validation service (GUI-010).

Guarantees:
- Validates 4-connected component reachability between start and goal.
- Prohibits start/goal placement on obstacles or out of bounds.
- Generates immutable scenario snapshots with deterministic instance hashes.
- Provides standard research scenarios (Bottleneck, Crossing, Corridor, Grid).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mapf.core.hashing import compute_instance_hash
from mapf.core.models import Point, SimulationSetting
from mapf.solvers.base import MAPFInstance


@dataclass(frozen=True)
class ScenarioSummary:
    """Summary metadata for a loaded or built-in scenario."""

    scenario_id: str
    name: str
    grid_width: int
    grid_height: int
    agent_count: int
    obstacle_count: int
    density: float
    setting: str
    instance_hash: str
    description: str


class ScenarioService:
    """Service managing scenario templates, validation, and MovingAI imports."""

    @staticmethod
    def get_built_in_scenarios() -> list[ScenarioSummary]:
        """Return summaries of built-in research benchmark scenarios."""
        scenarios = [
            ScenarioService.create_crossing_scenario(),
            ScenarioService.create_bottleneck_scenario(),
            ScenarioService.create_narrow_corridor_scenario(),
            ScenarioService.create_dense_grid_scenario(agent_count=4),
            ScenarioService.create_dense_grid_scenario(agent_count=8),
        ]
        summaries = []
        for s_id, name, desc, inst, setting in scenarios:
            h = compute_instance_hash(inst, setting)
            total_cells = inst.grid_width * inst.grid_height
            density = (
                round(len(inst.obstacles) / total_cells, 3) if total_cells > 0 else 0.0
            )
            summaries.append(
                ScenarioSummary(
                    scenario_id=s_id,
                    name=name,
                    grid_width=inst.grid_width,
                    grid_height=inst.grid_height,
                    agent_count=inst.agent_count,
                    obstacle_count=len(inst.obstacles),
                    density=density,
                    setting=setting.name,
                    instance_hash=h,
                    description=desc,
                )
            )
        return summaries

    @staticmethod
    def create_crossing_scenario() -> tuple[
        str, str, str, MAPFInstance, SimulationSetting
    ]:
        """Classic orthogonal crossing conflict: 2 agents crossing paths in 5x5."""
        starts = {"agent_0": Point(x=0, y=2), "agent_1": Point(x=2, y=0)}
        goals = {"agent_0": Point(x=4, y=2), "agent_1": Point(x=2, y=4)}
        inst = MAPFInstance(
            grid_width=5,
            grid_height=5,
            obstacles=set(),
            starts=starts,
            goals=goals,
        )
        return (
            "crossing-2a",
            "Orthogonal Crossing (2 Agents)",
            "Two agents crossing perpendicular paths at the central intersection.",
            inst,
            SimulationSetting.SETTING_1,
        )

    @staticmethod
    def create_bottleneck_scenario() -> tuple[
        str, str, str, MAPFInstance, SimulationSetting
    ]:
        """Wall with a single central gap: agents must negotiate priority."""
        obstacles = {
            Point(x=3, y=0),
            Point(x=3, y=1),
            Point(x=3, y=3),
            Point(x=3, y=4),
            Point(x=3, y=5),
            Point(x=3, y=6),
        }
        starts = {
            "agent_0": Point(x=1, y=2),
            "agent_1": Point(x=5, y=2),
        }
        goals = {
            "agent_0": Point(x=5, y=2),
            "agent_1": Point(x=1, y=2),
        }
        inst = MAPFInstance(
            grid_width=7,
            grid_height=7,
            obstacles=obstacles,
            starts=starts,
            goals=goals,
        )
        return (
            "bottleneck-2a",
            "Bottleneck Corridor (2 Agents)",
            "Single-cell constriction requiring one agent to wait or yield.",
            inst,
            SimulationSetting.SETTING_1,
        )

    @staticmethod
    def create_narrow_corridor_scenario() -> tuple[
        str, str, str, MAPFInstance, SimulationSetting
    ]:
        """Head-on collision in a narrow corridor with side pockets."""
        # Corridor at y=1 from x=1 to x=7, with a waiting pocket at (4, 0)
        obstacles = set()
        for x in range(9):
            obstacles.add(Point(x=x, y=0))
            obstacles.add(Point(x=x, y=2))
        obstacles.remove(Point(x=4, y=0))  # Side pocket

        starts = {"agent_0": Point(x=1, y=1), "agent_1": Point(x=7, y=1)}
        goals = {"agent_0": Point(x=7, y=1), "agent_1": Point(x=1, y=1)}
        inst = MAPFInstance(
            grid_width=9,
            grid_height=3,
            obstacles=obstacles,
            starts=starts,
            goals=goals,
        )
        return (
            "corridor-pocket-2a",
            "Corridor with Evacuation Pocket",
            "Head-on collision resolvable only by one agent yielding into the side pocket.",
            inst,
            SimulationSetting.SETTING_1,
        )

    @staticmethod
    def create_dense_grid_scenario(
        agent_count: int = 4,
    ) -> tuple[str, str, str, MAPFInstance, SimulationSetting]:
        """8x8 grid with scattered obstacles and multiple agents."""
        obstacles = {
            Point(x=2, y=2),
            Point(x=2, y=5),
            Point(x=5, y=2),
            Point(x=5, y=5),
        }
        all_starts = [
            Point(x=0, y=0),
            Point(x=7, y=7),
            Point(x=0, y=7),
            Point(x=7, y=0),
        ]
        all_goals = [Point(x=7, y=7), Point(x=0, y=0), Point(x=7, y=0), Point(x=0, y=7)]
        if agent_count > 4:
            all_starts.extend(
                [Point(x=1, y=3), Point(x=6, y=4), Point(x=3, y=1), Point(x=4, y=6)]
            )
            all_goals.extend(
                [Point(x=6, y=4), Point(x=1, y=3), Point(x=4, y=6), Point(x=3, y=1)]
            )

        starts = {f"agent_{i}": p for i, p in enumerate(all_starts[:agent_count])}
        goals = {f"agent_{i}": p for i, p in enumerate(all_goals[:agent_count])}

        inst = MAPFInstance(
            grid_width=8,
            grid_height=8,
            obstacles=obstacles,
            starts=starts,
            goals=goals,
        )
        return (
            f"grid-8x8-{agent_count}a",
            f"8x8 Grid ({agent_count} Agents)",
            f"Symmetric diagonal paths with central obstacle avoidance for {agent_count} agents.",
            inst,
            SimulationSetting.SETTING_1,
        )

    @staticmethod
    def validate_instance(
        inst: MAPFInstance, setting: SimulationSetting = SimulationSetting.SETTING_1
    ) -> list[str]:
        """Semantically validate a MAPF instance. Returns list of errors (empty if valid)."""
        errors: list[str] = []
        if not 1 <= len(inst.starts) <= 100:
            errors.append("A scenario must contain between 1 and 100 agents")
        if inst.starts.keys() != inst.goals.keys():
            errors.append("Start and goal agent IDs must match exactly")
        if not all(a and len(a) <= 64 for a in inst.starts):
            errors.append("Agent IDs must have 1 to 64 characters")

        if not (1 <= inst.grid_width <= 64 and 1 <= inst.grid_height <= 64):
            errors.append(
                f"Invalid grid dimensions: {inst.grid_width}x{inst.grid_height}"
            )
            return errors

        if any(
            not (0 <= p.x < inst.grid_width and 0 <= p.y < inst.grid_height)
            for p in inst.obstacles
        ):
            errors.append("Obstacle out of bounds")
        if not setting.disappear_at_target and len(set(inst.goals.values())) != len(
            inst.goals
        ):
            errors.append(
                "Shared goals are not possible when agents remain at their targets"
            )

        obs_set = {(p.x, p.y) for p in inst.obstacles}

        for aid, s in inst.starts.items():
            if not (0 <= s.x < inst.grid_width and 0 <= s.y < inst.grid_height):
                errors.append(f"Agent '{aid}' start ({s.x}, {s.y}) out of bounds")
            elif (s.x, s.y) in obs_set:
                errors.append(f"Agent '{aid}' start ({s.x}, {s.y}) on obstacle")

        for aid, g in inst.goals.items():
            if not (0 <= g.x < inst.grid_width and 0 <= g.y < inst.grid_height):
                errors.append(f"Agent '{aid}' goal ({g.x}, {g.y}) out of bounds")
            elif (g.x, g.y) in obs_set:
                errors.append(f"Agent '{aid}' goal ({g.x}, {g.y}) on obstacle")

        # Duplicate start/goal positions
        start_positions = list(inst.starts.values())
        if len(start_positions) != len({(p.x, p.y) for p in start_positions}):
            errors.append("Duplicate start positions detected among agents")

        from mapf.core.geometry import grid_index
        components = grid_index(inst.grid_width, inst.grid_height, frozenset(obs_set)).components
        for aid, start in inst.starts.items():
            if aid in inst.goals:
                goal = inst.goals[aid]
                component = components.get((start.x, start.y))
                if component is None or component != components.get((goal.x, goal.y)):
                    errors.append(f"No valid path exists between start and goal for agent '{aid}'")

        return errors

    @staticmethod
    def snapshot_instance(
        inst: MAPFInstance,
        setting: SimulationSetting,
        name: str = "custom",
    ) -> dict[str, Any]:
        """Create an immutable dictionary snapshot of a scenario with its hash."""
        h = compute_instance_hash(inst, setting)
        return {
            "name": name,
            "grid_width": inst.grid_width,
            "grid_height": inst.grid_height,
            "obstacles": [
                [p.x, p.y] for p in sorted(inst.obstacles, key=lambda p: (p.x, p.y))
            ],
            "agent_order": list(inst.starts),
            "starts": {aid: [p.x, p.y] for aid, p in inst.starts.items()},
            "goals": {aid: [p.x, p.y] for aid, p in inst.goals.items()},
            "setting": setting.name,
            "instance_hash": h,
        }
