#!/usr/bin/env python3
"""Example 1: Basic Decentralized MAPF Simulation.

Demonstrates setting up a 16x16 grid with 10 agents using HeatMap.
This direct API call has cooperative guards, not a parent process watchdog.
Use 04_supervised_study.py or mapf batch for durable supervised execution.
"""
from mapf import (
    CommitmentType,
    DecentralizedNegotiationSolver,
    MAPFInstance,
    SimulationConfig,
    SimulationSetting,
)
from mapf.core.movingai import generate_benchmark_map, generate_stern_scenario


def main() -> None:
    seed = 42
    grid_size = 16
    agent_count = 10

    print("=" * 60)
    print("  DEC-MAPF - Basic Simulation Example")
    print("=" * 60)

    # 1. Generate obstacle map
    obstacles = generate_benchmark_map(
        width=grid_size,
        height=grid_size,
        obstacle_density=0.10,
        seed=seed,
    )

    # 2. Assign agent start and goal pairs
    pairs = generate_stern_scenario(
        width=grid_size,
        height=grid_size,
        obstacles=obstacles,
        num_agents=agent_count,
        min_dist=4,
        max_dist=24,
        seed=seed,
    )
    starts = {f"Agent_{i + 1:02d}": pairs[i][0] for i in range(agent_count)}
    goals = {f"Agent_{i + 1:02d}": pairs[i][1] for i in range(agent_count)}

    instance = MAPFInstance(
        starts=starts,
        goals=goals,
        grid_width=grid_size,
        grid_height=grid_size,
        obstacles=obstacles,
    )

    # 3. Configure simulation: Setting 4 (Disappear=True, Wait=True)
    config = SimulationConfig(
        grid_width=grid_size,
        grid_height=grid_size,
        obstacles=obstacles,
        fov_size=5,
        setting=SimulationSetting.SETTING_4,
        commitment_type=CommitmentType.ZERO,
        initial_tokens=5,
        max_steps=100,
        random_seed=seed,
    )

    # 4. Solve using HeatMap agent
    solver = DecentralizedNegotiationSolver(strategy="HeatMap")
    solution = solver.solve(instance, config)

    print("\nResults:")
    print(f"  Success:                  {solution.success}")
    print(f"  Independently valid:      {solution.metrics['independent_validation']['is_valid']}")
    print(f"  Makespan (actions):       {solution.makespan if solution.success else 'Unavailable (not solved)'}")
    print(f"  Negotiations:             {solution.metrics.get('negotiation_count', 0)}")
    sharing = solution.metrics.get("information_sharing_rate")
    sharing_label = f"{100 * sharing:.2f}%" if sharing is not None else "Unavailable"
    print(f"  Information Sharing:      {sharing_label}")
    print(f"  Runtime:                  {solution.runtime_ms:.2f} ms")
    print("=" * 60)


if __name__ == "__main__":
    main()
