"""Explicit simulation deadlines override constructor defaults in both CT searches."""

from types import SimpleNamespace

import pytest

from mapf.core.models import Point, SimulationConfig
from mapf.solvers import cbs, eecbs
from mapf.solvers.base import MAPFInstance


@pytest.mark.parametrize("solver_case", [(cbs, cbs.CentralizedCBSSolver),
                                        (eecbs, eecbs.CentralizedEECBSSolver)])
@pytest.mark.parametrize("deadline_case", [(0.5, 3, False),
                                                           (3, 0.5, True), (0.5, None, True)])
def test_effective_deadline_uses_declared_configuration(monkeypatch, solver_case, deadline_case):
    module, solver = solver_case
    default, explicit, expected_timeout = deadline_case
    clock = iter([0.0])
    monkeypatch.setattr(module, "time", SimpleNamespace(perf_counter=lambda: next(clock, 1.0)))
    instance = MAPFInstance(grid_width=3, grid_height=2,
        starts={"a": Point(0, 0), "b": Point(2, 0)},
        goals={"a": Point(2, 0), "b": Point(0, 0)})
    configuration = {} if explicit is None else {"centralized_timeout_sec": explicit}
    result = solver(time_limit_sec=default).solve(instance, SimulationConfig(**configuration))
    assert result.success is not expected_timeout
    if expected_timeout:
        assert result.metrics["timeout"] is True
        assert result.metrics["termination_reason"] == "timeout"
    else:
        assert result.metrics["independent_validation"]["is_valid"] is True
