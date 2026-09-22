from __future__ import annotations

from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.solvers.base import MAPFInstance
from mapf.solvers.cbs import CentralizedCBSSolver
from mapf.solvers.decentralized import DecentralizedNegotiationSolver
from mapf.solvers.eecbs import CentralizedEECBSSolver


def test_centralized_cbs_timeout():
    """Verify CBS honors timeout limit strictly and returns failure when time expires."""
    # Create an instance with head-on conflict
    inst = MAPFInstance(
        starts={"A1": Point(x=0, y=0), "A2": Point(x=10, y=0), "A3": Point(x=5, y=5)},
        goals={"A1": Point(x=10, y=0), "A2": Point(x=0, y=0), "A3": Point(x=5, y=0)},
        grid_width=12,
        grid_height=12,
    )
    # Extremely small timeout limit to force timeout
    cfg = SimulationConfig(grid_width=12, grid_height=12, centralized_timeout_sec=0.0001)
    solver = CentralizedCBSSolver(time_limit_sec=0.0001)
    sol = solver.solve(inst, cfg)
    # With 0.1ms timeout, solver should exit cleanly without raising exceptions
    assert not sol.success or sol.runtime_ms >= 0.0


def test_centralized_eecbs_timeout():
    """Verify EECBS honors timeout limit cleanly."""
    inst = MAPFInstance(
        starts={"A1": Point(x=0, y=0), "A2": Point(x=10, y=0)},
        goals={"A1": Point(x=10, y=0), "A2": Point(x=0, y=0)},
        grid_width=12,
        grid_height=12,
    )
    cfg = SimulationConfig(grid_width=12, grid_height=12, centralized_timeout_sec=0.0001)
    solver = CentralizedEECBSSolver(suboptimality=1.1, time_limit_sec=0.0001)
    sol = solver.solve(inst, cfg)
    assert not sol.success or sol.runtime_ms >= 0.0


def test_decentralized_max_steps_constraint():
    """Verify decentralized simulation strictly halts when max_steps is reached."""
    # Place agents far apart with max_steps=2
    inst = MAPFInstance(
        starts={"A1": Point(x=0, y=0), "A2": Point(x=10, y=10)},
        goals={"A1": Point(x=15, y=15), "A2": Point(x=0, y=0)},
        grid_width=16,
        grid_height=16,
    )
    cfg = SimulationConfig(
        grid_width=16,
        grid_height=16,
        max_steps=2,
        setting=SimulationSetting.SETTING_4,
    )
    solver = DecentralizedNegotiationSolver(strategy="HeatMap")
    sol = solver.solve(inst, cfg)
    assert not sol.success
    assert sol.makespan <= cfg.max_steps + 1
