#!/usr/bin/env python3
"""Example 3: Centralized vs. Decentralized Solver Comparison.

Executes HeatMap (Decentralized Negotiation) and Centralized CBS on the
identical teaching instance and seed, printing qualified descriptive metrics.
This direct API illustration has no supervising parent process. Use the batch
tutorial or 04_supervised_study.py for durable bounded experiments.
"""
from mapf import (
    CentralizedCBSSolver,
    CommitmentType,
    DecentralizedNegotiationSolver,
    MAPFInstance,
    SimulationConfig,
    SimulationSetting,
)
from mapf.core.movingai import generate_benchmark_map, generate_stern_scenario


def main() -> None:
    seed = 42
    grid_size = 12
    agent_count = 6

    print("=" * 65)
    print("  MAPF: Centralized vs. Decentralized Teaching Example")
    print(f"  Grid: {grid_size}x{grid_size} | Agents: {agent_count} | Seed: {seed}")
    print("=" * 65)

    obstacles = generate_benchmark_map(
        width=grid_size,
        height=grid_size,
        obstacle_density=0.10,
        seed=seed,
    )
    pairs = generate_stern_scenario(
        width=grid_size,
        height=grid_size,
        obstacles=obstacles,
        num_agents=agent_count,
        min_dist=3,
        max_dist=16,
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
        centralized_timeout_sec=30.0,
    )

    # 1. Decentralized HeatMap Solver
    solver_dec = DecentralizedNegotiationSolver(strategy="HeatMap")
    sol_dec = solver_dec.solve(instance, config)

    # 2. Centralized CBS Solver
    solver_cbs = CentralizedCBSSolver(time_limit_sec=30.0)
    sol_cbs = solver_cbs.solve(instance, config)

    print("\nComparison Results:")
    print("  Metric                      HeatMap (Decentralized)   CBS (Centralized)")
    print("  -------------------------   -----------------------   -----------------")
    print(f"  Success:                    {'YES' if sol_dec.success else 'NO':<25} {'YES' if sol_cbs.success else 'NO'}")
    common_solved = sol_dec.success and sol_cbs.success
    print(f"  Both independently solved:  {common_solved}")
    if common_solved:
        print(f"  Makespan (actions):         {sol_dec.makespan:<25} {sol_cbs.makespan}")
        print(f"  Sum of Costs:               {sol_dec.sum_of_costs:<25} {sol_cbs.sum_of_costs}")
    else:
        print("  Paired path costs:          Unavailable: both methods must solve validly")
    print(f"  Runtime (ms):               {sol_dec.runtime_ms:<25.2f} {sol_cbs.runtime_ms:.2f}")
    print(f"  Negotiations:               {sol_dec.metrics.get('negotiation_count', 0):<25} N/A (Centralized)")
    sharing = sol_dec.metrics.get("information_sharing_rate")
    sharing_label = f"{100 * sharing:.2f}%" if sharing is not None else "Unavailable"
    print(f"  Broadcast Sharing Rate:     {sharing_label:<25} Unavailable (not instrumented)")
    print("  One generated instance: descriptive only, no statistical ranking.")
    print("=" * 65)


if __name__ == "__main__":
    main()
