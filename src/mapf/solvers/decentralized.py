from __future__ import annotations

import time
from typing import Literal, get_args

from mapf.agents.base import BaseAgent
from mapf.agents.greedy import ConcederAgent, GreedyAgent
from mapf.agents.heatmap import HeatMapAgent
from mapf.agents.path_aware import PathAwareAgent
from mapf.core.models import Path, SimulationConfig
from mapf.engine.world import WorldSimulation
from mapf.solvers.base import MAPFInstance, MAPFSolution, MAPFSolverProtocol
from mapf.solvers.validation import validated_solver

StrategyType = Literal["PathAware", "HeatMap", "Greedy", "Conceder"]


class DecentralizedNegotiationSolver(MAPFSolverProtocol):
    """Decentralized Multi-Agent Path Finding solver using automated negotiation."""

    def __init__(self, strategy: StrategyType = "PathAware") -> None:
        if strategy not in get_args(StrategyType):
            raise ValueError(
                f"Unsupported strategy: {strategy!r}. Choose one of {', '.join(get_args(StrategyType))}"
            )
        self.strategy = strategy
        self._name = f"Decentralized Negotiation ({strategy})"

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_centralized(self) -> bool:
        return False

    @validated_solver
    def solve(self, instance: MAPFInstance, config: SimulationConfig) -> MAPFSolution:
        start_time = time.perf_counter()
        if instance.obstacles and not config.obstacles:
            config = config.model_copy(update={"obstacles": instance.obstacles})
        sim = WorldSimulation(config)

        # Instantiate agents according to selected strategy
        for a_id, st in instance.starts.items():
            gl = instance.goals[a_id]
            agent: BaseAgent
            if self.strategy == "PathAware":
                agent = PathAwareAgent(
                    a_id,
                    st,
                    gl,
                    config.initial_tokens,
                    commitment_type=config.commitment_type,
                )
            elif self.strategy == "HeatMap":
                agent = HeatMapAgent(
                    a_id,
                    st,
                    gl,
                    config.initial_tokens,
                    config.fov_size,
                    commitment_type=config.commitment_type,
                )
            elif self.strategy == "Greedy":
                agent = GreedyAgent(
                    a_id,
                    st,
                    gl,
                    config.initial_tokens,
                    commitment_type=config.commitment_type,
                )
            else:
                agent = ConcederAgent(
                    a_id,
                    st,
                    gl,
                    config.initial_tokens,
                    commitment_type=config.commitment_type,
                )

            sim.add_agent(agent)

        results = sim.run()
        runtime_ms = (time.perf_counter() - start_time) * 1000.0

        # Construct final executed paths
        paths: dict[str, Path] = {
            a_id: Path(points=pts) for a_id, pts in results["path_history"].items()
        }

        makespan = max(p.length for p in paths.values()) if paths else 0
        sum_of_costs = sum(p.length for p in paths.values()) if paths else 0

        return MAPFSolution(
            solver_name=self.name,
            is_centralized=False,
            success=results["success"],
            paths=paths,
            makespan=makespan,
            sum_of_costs=sum_of_costs,
            runtime_ms=runtime_ms,
            metrics={
                "collision_count": results.get("collision_count", 0),
                "solved_count": results.get("solved_count", 0),
                "total_agents": results.get("total_agents", 0),
                "negotiation_count": results["negotiation_count"],
                "successful_negotiations": results["successful_negotiations"],
                "information_sharing_rate": results["information_sharing_rate"],
                "legacy_reconstructed_IS_proxy": None,
                "initial_sum_of_costs": results.get(
                    "initial_path_length", sum_of_costs
                ),
                "norm_path_diff": results.get("norm_path_diff", 0.0),
                "broadcast_ratio": round(results.get("broadcast_ratio", 0.0), 4),
                "token_exchanges": results.get("token_exchanges", 0),
                "nego_by_step": results.get("nego_by_step", {}),
                "frames": results.get("frames", []),
                "initial_snapshot": results.get("initial_snapshot", {}),
                "solver_diagnostics": results["solver_diagnostics"],
                "heat_recording": results["heat_recording"],
                "communication": {key: results[key] for key in (
                    "metric_version", "information_sharing_definition", "message_count", "payload_bytes",
                    "transmitted_cells", "transfer_count", "final_token_balances", "token_gini",
                    "spacetime_information_sharing_rate", "safety_interventions",
                    "all_message_information_sharing_rate", "token_exchanges", "broadcast_ratio", "termination_reason",
                )},
            },
        )
