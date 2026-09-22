from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mapf.analytics.logger import ExperimentLogger
from mapf.analytics.plots import generate_jaamas_comparison_plot
from mapf.gui.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as value:
        yield value


def test_gui_simulation_endpoint(client):

    payload = {
        "grid_width": 10,
        "grid_height": 10,
        "agent_count": 4,
        "solver": "PathAware",
        "fov_size": 5,
        "obstacle_density": 0.0,
        "setting": 4,
        "initial_tokens": 5,
        "max_steps": 50,
        "random_seed": 42,
    }

    response = client.post("/api/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_agents"] == 4
    assert len(data["paths"]) == 4
    assert "information_sharing_rate" in data


def test_analytics_logger_and_plot(tmp_path: Path):
    logger = ExperimentLogger(log_dir=tmp_path)
    logger.log_run(
        scenario_id="sc_01",
        setting=4,
        agent_type="PathAware",
        agent_count=20,
        grid_size=16,
        fov_size=5,
        success=True,
        total_steps=18,
        negotiation_count=5,
        successful_negotiations=5,
        total_path_length=36,
        information_sharing_rate=0.45,
    )

    df = logger.to_polars()
    assert len(df) == 1
    assert df["success"][0] is True

    summary = logger.summarize_by_strategy()
    assert len(summary) == 1
    assert summary["solution_rate"][0] == 1.0

    # Test plot generation
    plot_file = tmp_path / "plot.svg"
    data = {
        "PathAware": [0.98, 0.75, 0.30, 0.09],
        "HeatMap": [0.99, 0.98, 0.92, 0.67],
    }
    out = generate_jaamas_comparison_plot(
        data=data,
        agent_counts=[20, 40, 60, 80],
        output_path=plot_file,
    )
    assert out.exists()
    assert out.stat().st_size > 0


def test_gui_presets_and_batch_endpoints(client):

    # 1. Presets endpoint
    presets_resp = client.get("/api/presets")
    assert presets_resp.status_code == 200
    presets = presets_resp.json()
    assert len(presets) >= 3

    # 2. Simulate with compare_solver
    payload = {
        "grid_width": 8,
        "grid_height": 8,
        "agent_count": 2,
        "solver": "HeatMap",
        "compare_solver": "PathAware",
        "fov_size": 5,
        "obstacle_density": 0.0,
        "setting": 4,
        "initial_tokens": 5,
        "max_steps": 30,
        "random_seed": 42,
    }
    sim_resp = client.post("/api/simulate", json=payload)
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()
    assert "primary" in sim_data
    assert "comparison" in sim_data
    assert sim_data["comparison"]["solver_key"] == "PathAware"

    # 3. Batch benchmark start & status
    batch_resp = client.post("/api/benchmark/start", json={"suite_name": "quick_test"})
    assert batch_resp.status_code == 410
    assert "mapf batch" in batch_resp.json()["detail"]
