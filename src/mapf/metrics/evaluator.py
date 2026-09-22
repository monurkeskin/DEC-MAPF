from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from mapf.core.models import Path, Point


class MAPFRunMetrics(BaseModel):
    """Detailed benchmark metrics for a single simulation run."""

    scenario_id: str
    success: bool
    agent_count: int
    grid_size: int
    setting: int
    total_steps: int
    makespan: int
    sum_of_costs: int
    optimality_gap: float | None = None
    negotiation_count: int = 0
    successful_negotiation_rate: float = 0.0
    information_sharing_rate: float = 0.0


def calculate_information_sharing_rate(
    solution_paths: dict[str, list[Point]],
    broadcast_history: list[dict[str, Path]],
    fov_size: int = 5,
    is_heatmap: bool = False,
    negotiation_history: list[dict[str, Any]] | None = None,
) -> float:
    """Legacy spatial disclosure proxy reconstructed from paths and FoV geometry.

    Recipient delivery and payloads are not recorded by these inputs. Repeated
    visits collapse to spatial Point sets, and negotiation proposals contribute
    only if explicit shared_points fields were supplied. This is not a measured
    implementation of the paper's information-sharing protocol. The GUI marks
    empirical IS unavailable and retains this value only as a named legacy proxy.
    """
    agent_ids = list(solution_paths.keys())
    k = len(agent_ids)
    if k <= 1:
        return 0.0

    radius = fov_size // 2
    max_steps = min(
        len(broadcast_history),
        max((len(p) for p in solution_paths.values()), default=0),
    )

    # Track pairwise transmitted points: (sender_j, receiver_i) -> set of points
    transmitted: dict[tuple[str, str], set[Point]] = {}

    # Shared lookahead horizon is determined by FoV broadcast size
    lookahead_len = fov_size

    for t in range(max_steps):
        step_broadcast = broadcast_history[t] if t < len(broadcast_history) else {}
        for j_id in agent_ids:
            if t >= len(solution_paths[j_id]):
                continue
            pos_j = solution_paths[j_id][t]
            path_j = step_broadcast.get(j_id)
            if not path_j or not path_j.points:
                continue

            shared_points_set = set(path_j.points[:lookahead_len])

            for i_id in agent_ids:
                if i_id == j_id:
                    continue
                if t >= len(solution_paths[i_id]):
                    continue
                pos_i = solution_paths[i_id][t]

                # Check if peer i is within FoV of agent j
                if (
                    abs(pos_i.x - pos_j.x) <= radius
                    and abs(pos_i.y - pos_j.y) <= radius
                ):
                    key = (j_id, i_id)
                    if key not in transmitted:
                        transmitted[key] = set()
                    transmitted[key].update(shared_points_set)

    # Incorporate verifiable bilateral negotiation proposal exchanges if present in history
    if negotiation_history:
        for n in negotiation_history:
            a_id, b_id = n.get("agent_a", ""), n.get("agent_b", "")
            # If explicit proposal coordinates were logged, record them
            pts_a = n.get("shared_points_a")
            pts_b = n.get("shared_points_b")
            if pts_a and a_id and b_id:
                transmitted.setdefault((a_id, b_id), set()).update(pts_a)
            if pts_b and a_id and b_id:
                transmitted.setdefault((b_id, a_id), set()).update(pts_b)

    agent_is_rates: list[float] = []

    for j_id in agent_ids:
        sol_pts = set(solution_paths[j_id])
        if not sol_pts:
            continue

        pairwise_ratios: list[float] = []
        for i_id in agent_ids:
            if i_id == j_id:
                continue
            sent_pts = transmitted.get((j_id, i_id), set())
            ratio = float(len(sent_pts & sol_pts)) / float(len(sol_pts))
            pairwise_ratios.append(min(1.0, ratio))

        # Average across all other (k - 1) agents as per Equation 3
        is_j = sum(pairwise_ratios) / float(k - 1) if pairwise_ratios else 0.0
        agent_is_rates.append(is_j)

    return sum(agent_is_rates) / float(len(agent_is_rates)) if agent_is_rates else 0.0


def evaluate_batch_results(
    runs: list[dict[str, Any]],
    optimal_costs: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Aggregate statistics across batch runs matching JAAMAS 2024 Table 1 & Table 2 standards."""
    total_runs = len(runs)
    if total_runs == 0:
        return {"solution_rate": 0.0, "total_runs": 0}

    solved_runs = [r for r in runs if r.get("success", False)]
    solution_rate = float(len(solved_runs)) / float(total_runs)

    makespans = [r.get("total_steps", 0) for r in solved_runs]
    avg_makespan = sum(makespans) / float(len(makespans)) if makespans else 0.0

    nego_counts = [r.get("negotiation_count", 0) for r in runs]
    avg_negotiations = (
        sum(nego_counts) / float(len(nego_counts)) if nego_counts else 0.0
    )

    # Optimality Gap: (|pi| - |pi*|) / |pi*|
    opt_gaps: list[float] = []
    if optimal_costs:
        for r in solved_runs:
            s_id = str(r.get("scenario_id", ""))
            if s_id in optimal_costs:
                opt = optimal_costs[s_id]
                actual = r.get("total_path_length", 0)
                if opt > 0:
                    gap = float(actual - opt) / float(opt)
                    opt_gaps.append(gap)

    avg_opt_gap = sum(opt_gaps) / float(len(opt_gaps)) if opt_gaps else None

    return {
        "total_runs": total_runs,
        "solved_runs": len(solved_runs),
        "solution_rate": round(solution_rate, 4),
        "average_makespan": round(avg_makespan, 2),
        "average_negotiations": round(avg_negotiations, 2),
        "average_optimality_gap": round(avg_opt_gap, 4)
        if avg_opt_gap is not None
        else None,
    }
