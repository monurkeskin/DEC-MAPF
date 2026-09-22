"""Public researcher entrypoints reject misleading method identities."""

from typing import Any

import pytest

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.solvers import SolverRegistry
from mapf.solvers.decentralized import DecentralizedNegotiationSolver
from mapf.solvers.registry import register_solver, solver_metadata


@pytest.mark.parametrize("strategy", ["HeatMapp", "heatmap", "", None])
def test_unknown_direct_strategy_fails_before_simulation(strategy: Any) -> None:
    with pytest.raises(ValueError, match="Unsupported strategy"):
        DecentralizedNegotiationSolver(strategy=strategy)


@pytest.mark.parametrize("strategy", ["HeatMap", "PathAware", "Greedy", "Conceder"])
def test_supported_direct_strategy_keeps_identity(strategy: Any) -> None:
    solver = DecentralizedNegotiationSolver(strategy=strategy)
    assert solver.name == f"Decentralized Negotiation ({strategy})"


def test_duplicate_registration_cannot_replace_a_published_method():
    original = solver_metadata("HeatMap")
    with pytest.raises(ValueError, match="already registered"):
        register_solver("heatmap")(original.factory)
    assert solver_metadata("HeatMap") is original


def test_capability_defaults_come_from_request_contract():
    for cap in SolverRegistry.list_capabilities():
        for parameter in cap.parameters:
            assert parameter.default == JobSubmissionRequest.model_fields[parameter.name].default


def test_factory_input_binding_does_not_depend_on_solver_name():
    from mapf.solvers.cbs import CentralizedCBSSolver
    register_solver("ContractTestCBS", is_centralized=True,
                    constructor_inputs=(("timeout_sec", "time_limit_sec"),))(CentralizedCBSSolver)
    solver = SolverRegistry.create_solver("ContractTestCBS", timeout_sec=17)
    assert solver.time_limit_sec == 17
