"""Versioned action costs, independent shortest-path detour and matched references."""

from __future__ import annotations

from typing import Any

from mapf.core.models import Path
from mapf.core.space_time_grid import compute_static_distance_table
from mapf.solvers.base import MAPFInstance

METRIC_VERSION = "delivered-metrics-v2"


def trajectory_costs(instance: MAPFInstance, paths: dict[str, Path]) -> dict[str, Any]:
    arrivals: dict[str, int | None] = {}
    recorded = 0
    lower_bound = 0
    reachable = True
    for aid, start in instance.starts.items():
        path = paths.get(aid)
        arrivals[aid] = next((i for i, p in enumerate(path.points) if p == instance.goals[aid]), None) if path else None
        recorded += path.length if path else 0
        table = compute_static_distance_table(instance.grid_width, instance.grid_height,
                                              instance.obstacles, instance.goals[aid])
        distance = table.get((start.x, start.y))
        if distance is None:
            reachable = False
        else:
            lower_bound += distance
    complete = all(t is not None for t in arrivals.values()) and bool(arrivals)
    cost = sum(t for t in arrivals.values() if t is not None) if complete else None
    detour = (cost / lower_bound - 1) if cost is not None and reachable and lower_bound > 0 else (
        0.0 if cost == 0 and reachable else None
    )
    return {"metric_version": METRIC_VERSION, "arrival_ticks": arrivals,
            "action_sum_of_costs": cost, "action_makespan": max((t for t in arrivals.values() if t is not None), default=0) if complete else None,
            "recorded_action_count": recorded, "independent_shortest_path_sum": lower_bound if reachable else None,
            "individual_detour_ratio": detour,
            "paper_eq2": None, "certified_optimality_gap": None}


def certified_optimality_gap(cost: int, reference_cost: int, *, identical_instance: bool,
                             reference_is_optimal: bool) -> float | None:
    if not identical_instance or not reference_is_optimal or reference_cost < 0:
        return None
    if reference_cost == 0:
        return 0.0 if cost == 0 else None
    if cost < reference_cost:
        raise ValueError("Admissible cost is below the claimed optimal reference")
    return cost / reference_cost - 1
