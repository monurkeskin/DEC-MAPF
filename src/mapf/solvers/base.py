from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from mapf.core.models import Path, Point, SimulationConfig


class MAPFInstance(BaseModel):
    """Problem instance definition for any MAPF solver."""
    model_config = ConfigDict(frozen=True)

    starts: dict[str, Point]
    goals: dict[str, Point]
    grid_width: int
    grid_height: int
    obstacles: set[Point] = Field(default_factory=set)

    @property
    def agent_count(self) -> int:
        return len(self.starts)

    @property
    def instance_hash(self) -> str:
        from mapf.core.hashing import compute_instance_hash

        return compute_instance_hash(self)


class MAPFSolution(BaseModel):
    """Standardized solution structure returned by all centralized and decentralized solvers."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    solver_name: str
    is_centralized: bool
    success: bool
    paths: dict[str, Path] = Field(default_factory=dict)
    makespan: int = 0
    sum_of_costs: int = 0
    runtime_ms: float = 0.0
    instance_hash: str = ""
    run_id: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class MAPFSolverProtocol(Protocol):
    """Unified solver contract for both Centralized algorithms and Decentralized agent protocols."""

    @property
    def name(self) -> str: ...

    @property
    def is_centralized(self) -> bool: ...

    def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution: ...
