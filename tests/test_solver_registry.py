from __future__ import annotations

import pytest

from mapf.core.models import SimulationConfig
from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol
from mapf.solvers.registry import get_solver, list_solvers, register_solver


def test_list_solvers_contains_builtins() -> None:
    solvers = list_solvers()
    assert "HeatMap" in solvers
    assert "PathAware" in solvers
    assert "CBS" in solvers
    assert "EECBS" in solvers
    assert "Prioritized" in solvers


def test_get_solver_instantiation() -> None:
    heatmap = get_solver("HeatMap")
    assert "heatmap" in heatmap.name.lower()
    assert not heatmap.is_centralized

    cbs = get_solver("CBS")
    assert "cbs" in cbs.name.lower()
    assert cbs.is_centralized


def test_register_custom_solver() -> None:
    @register_solver("DummySolver", is_centralized=True, description="Test custom solver")
    class DummySolver(MAPFSolverProtocol):
        @property
        def name(self) -> str:
            return "DummySolver"

        @property
        def is_centralized(self) -> bool:
            return True

        def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution:
            return MAPFSolution(
                solver_name=self.name,
                is_centralized=True,
                success=True,
            )

    solvers = list_solvers()
    assert "DummySolver" in solvers
    inst = get_solver("dummysolver")
    assert inst.name == "DummySolver"


def test_get_unknown_solver_raises() -> None:
    with pytest.raises(KeyError, match="not found in registry"):
        get_solver("NonExistentSolverXYZ")
