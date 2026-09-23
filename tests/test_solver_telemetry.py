"""Integration tests for DecentralizedNegotiationSolver with active telemetry."""

from __future__ import annotations

from pathlib import Path

from mapf.analytics.post_simulation import (
    compute_spatial_hotspots,
    load_events_as_polars,
)
from mapf.core.models import Point, SimulationConfig, SimulationSetting
from mapf.solvers.base import MAPFInstance
from mapf.solvers.decentralized import DecentralizedNegotiationSolver
from mapf.telemetry.logger import AsyncExperimentLogger


def test_solver_with_active_telemetry(tmp_path: Path) -> None:
    # 4 agents in a simple crossing setup
    starts = {
        "a0": Point(0, 2),
        "a1": Point(4, 2),
        "a2": Point(2, 0),
        "a3": Point(2, 4),
    }
    goals = {
        "a0": Point(4, 2),
        "a1": Point(0, 2),
        "a2": Point(2, 4),
        "a3": Point(2, 0),
    }
    instance = MAPFInstance(
        starts=starts,
        goals=goals,
        grid_width=8,
        grid_height=8,
        obstacles=set(),
    )

    log_dir = tmp_path / "telemetry_logs"
    with AsyncExperimentLogger(output_dir=log_dir, run_id="crossing_test") as logger:
        config = SimulationConfig(
            grid_width=8,
            grid_height=8,
            setting=SimulationSetting.SETTING_4,
            max_steps=30,
            enable_telemetry=True,
            telemetry_hook=logger.hook,
        )

        solver = DecentralizedNegotiationSolver(strategy="HeatMap")
        sol = solver.solve(instance, config)
        assert sol.success

    events_file = logger.events_file_path
    assert events_file.exists()

    df = load_events_as_polars(events_file)
    assert not df.is_empty()

    event_types = set(df["event_type"].to_list())
    assert "MOVE" in event_types
    assert "BROADCAST" in event_types

    hotspots = compute_spatial_hotspots(df, 8, 8)
    assert "density_matrix" in hotspots
