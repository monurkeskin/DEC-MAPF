from mapf.agents.heatmap import HeatMapAgent
from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import (
    Point,
    SimulationConfig,
    SimulationSetting,
)
from mapf.engine.world import WorldSimulation
from mapf.metrics.evaluator import (
    calculate_information_sharing_rate,
    evaluate_batch_results,
)


def test_world_simulation_two_crossing_agents():
    """Two agents cross each other in a 8x8 grid."""
    config = SimulationConfig(
        grid_width=8,
        grid_height=8,
        setting=SimulationSetting.SETTING_4,
        max_steps=50,
    )
    sim = WorldSimulation(config)

    # Agent 1 moves (0, 3) -> (7, 3)
    # Agent 2 moves (3, 0) -> (3, 7)
    # Both shortest routes reach (3, 3) at t=3.
    a1 = PathAwareAgent("A1", Point(x=0, y=3), Point(x=7, y=3), initial_tokens=5)
    a2 = HeatMapAgent("A2", Point(x=3, y=0), Point(x=3, y=7), initial_tokens=5)

    sim.add_agent(a1)
    sim.add_agent(a2)

    results = sim.run()

    assert results["success"] is True
    assert results["solved_count"] == 2
    assert a1.get_state().reached_goal is True
    assert a2.get_state().reached_goal is True

    # Check Information Sharing Rate
    is_rate = calculate_information_sharing_rate(
        results["path_history"], sim._broadcast_history
    )
    assert 0.0 <= is_rate <= 1.0


def test_batch_evaluation():
    mock_runs = [
        {
            "scenario_id": "s1",
            "success": True,
            "total_steps": 12,
            "negotiation_count": 2,
            "total_path_length": 24,
        },
        {
            "scenario_id": "s2",
            "success": True,
            "total_steps": 14,
            "negotiation_count": 3,
            "total_path_length": 28,
        },
        {
            "scenario_id": "s3",
            "success": False,
            "total_steps": 50,
            "negotiation_count": 5,
            "total_path_length": 40,
        },
    ]
    summary = evaluate_batch_results(mock_runs)
    assert summary["total_runs"] == 3
    assert summary["solved_runs"] == 2
    assert summary["solution_rate"] == 0.6667
