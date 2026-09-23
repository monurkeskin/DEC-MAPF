"""Seeded synthetic maps and reachable rosters, independent of file imports.

Column-major cell ordering and the sequence of rejected random draws are part
of the reproducibility contract. These generators do not reconstruct an
archived paper population.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field

from mapf.core.geometry import Cell, grid_index
from mapf.core.models import Point


def generate_benchmark_map(
    width: int,
    height: int,
    obstacle_density: float = 0.0,
    seed: int = 42,
) -> set[Point]:
    """Generate a synthetic, uniformly sampled obstacle map, not a MovingAI import.

    Use density 0.0 for an empty grid, 0.10 for approximately 10% blocked
    cells, or 0.20 for approximately 20%. Matching a density does not
    reconstruct a particular archived map.
    """
    dimensions_valid = min(width, height) > 0
    if not dimensions_valid or not 0 <= obstacle_density < 1:
        raise ValueError("Positive dimensions and obstacle density in [0,1) required")
    if obstacle_density == 0.0:
        return set()

    rng = random.Random(seed)
    total_cells = width * height
    num_obstacles = int(total_cells * obstacle_density)

    all_coords = [Point(x=x, y=y) for x in range(width) for y in range(height)]
    obstacles = set(rng.sample(all_coords, num_obstacles))
    return obstacles


def generate_stern_scenario(
    width: int,
    height: int,
    obstacles: set[Point],
    num_agents: int,
    min_dist: int = 4,
    max_dist: int = 24,
    seed: int = 42,
    max_attempts: int = 5000,
) -> list[tuple[Point, Point]]:
    """Sample synthetic reachable start/goal pairs without relaxing requested bounds.

    Starts and goals are unique within their respective sets and lie in the
    same traversable component. Their Manhattan distance must lie within
    [min_dist, max_dist]; this filter is not an obstacle-aware path length.
    Preserve rejected draws and cell order when changing the implementation,
    because both affect the seeded population.
    """
    rng = random.Random(seed)
    limits = _SamplingLimits(num_agents, min_dist, max_dist, max_attempts)
    limits.validate(width, height)
    traversable = _traversable_cells(width, height, obstacles)
    limits.require_capacity(len(traversable), width, height)

    geometry = grid_index(width, height, frozenset((p.x, p.y) for p in obstacles))
    sampler = _ScenarioSampler(
        traversable, geometry.components, rng, min_dist, max_dist
    )
    pairs = sampler.sample(num_agents, max_attempts)
    limits.require_completion(len(pairs))

    return pairs


@dataclass(frozen=True)
class _SamplingLimits:
    """Reject infeasible requests or incomplete draws without relaxing bounds."""

    agents: int
    min_dist: int
    max_dist: int
    attempts: int

    def validate(self, width: int, height: int) -> None:
        dimensions_valid = min(width, height) > 0
        population_valid = self.agents > 0 and 0 <= self.min_dist <= self.max_dist
        if not dimensions_valid or not population_valid:
            raise ValueError(
                "Invalid synthetic scenario dimensions, agent count or distance range"
            )

    def require_capacity(self, available: int, width: int, height: int) -> None:
        if available < self.agents:
            raise ValueError(
                f"Not enough traversable cells ({available}) for {self.agents} agents on {width}x{height} grid."
            )

    def require_completion(self, count: int) -> None:
        if count < self.agents:
            raise ValueError(
                f"Could not sample {self.agents} mutually reachable pairs within distance range "
                f"[{self.min_dist}, {self.max_dist}] after {self.attempts} attempts. Only {count} pairs found."
            )


def _traversable_cells(width: int, height: int, obstacles: set[Point]) -> list[Point]:
    """Column-major ordering is part of the seeded sampling contract."""
    return [
        Point(x=x, y=y)
        for x in range(width)
        for y in range(height)
        if Point(x=x, y=y) not in obstacles
    ]


@dataclass
class _ScenarioSampler:
    """Own uniqueness state while preserving the seeded draw/rejection order."""

    cells: list[Point]
    components: Mapping[Cell, int]
    rng: random.Random
    min_dist: int
    max_dist: int
    starts: set[Point] = field(default_factory=set)
    goals: set[Point] = field(default_factory=set)

    def sample(self, count: int, max_attempts: int) -> list[tuple[Point, Point]]:
        pairs: list[tuple[Point, Point]] = []
        attempts = 0
        while len(pairs) < count and attempts < max_attempts:
            attempts += 1
            pair = self._draw_pair()
            if pair is not None:
                self.starts.add(pair[0])
                self.goals.add(pair[1])
                pairs.append(pair)
        return pairs

    def _draw_pair(self) -> tuple[Point, Point] | None:
        start = self.rng.choice(self.cells)
        if start in self.starts:
            return None
        goal = self.rng.choice(self.cells)
        if goal in self.goals or goal == start:
            return None
        if self.components[(start.x, start.y)] != self.components[(goal.x, goal.y)]:
            return None
        if not self.min_dist <= start.manhattan_distance(goal) <= self.max_dist:
            return None
        return start, goal
