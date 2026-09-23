from __future__ import annotations

from dataclasses import dataclass, field
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
    if len(solution_paths) <= 1:
        return 0.0
    proxy = _SpatialDisclosureProxy(solution_paths, fov_size)
    proxy.observe_broadcasts(broadcast_history)
    proxy.observe_proposals(negotiation_history or [])
    return proxy.rate()


@dataclass
class _SpatialDisclosureProxy:
    """Legacy spatial sets; separate geometric inference from explicit proposals."""

    paths: dict[str, list[Point]]
    fov_size: int
    transmitted: dict[tuple[str, str], set[Point]] = field(default_factory=dict)

    def observe_broadcasts(self, history: list[dict[str, Path]]) -> None:
        max_steps = min(len(history), max((len(p) for p in self.paths.values()), default=0))
        for tick in range(max_steps):
            positions = {aid: points[tick] for aid, points in self.paths.items() if tick < len(points)}
            self._observe_step(history[tick], positions)

    def _observe_step(self, broadcasts: dict[str, Path], positions: dict[str, Point]) -> None:
        for sender, position in positions.items():
            path = broadcasts.get(sender)
            if not path or not path.points:
                continue
            shared = set(path.points[:self.fov_size])
            self._share_with_visible_peers(sender, position, shared, positions)

    def _share_with_visible_peers(self, sender: str, position: Point, shared: set[Point],
                                  positions: dict[str, Point]) -> None:
        radius = self.fov_size // 2
        for receiver, other in positions.items():
            if receiver == sender:
                continue
            visible = abs(position.x - other.x) <= radius and abs(position.y - other.y) <= radius
            if visible:
                self.transmitted.setdefault((sender, receiver), set()).update(shared)

    def observe_proposals(self, history: list[dict[str, Any]]) -> None:
        for record in history:
            a_id, b_id = record.get("agent_a", ""), record.get("agent_b", "")
            if not a_id or not b_id:
                continue
            self._record_proposal(a_id, b_id, record.get("shared_points_a"))
            self._record_proposal(b_id, a_id, record.get("shared_points_b"))

    def _record_proposal(self, sender: str, receiver: str, points: Any) -> None:
        if points:
            self.transmitted.setdefault((sender, receiver), set()).update(points)

    def rate(self) -> float:
        rates = [self._sender_rate(sender, set(points))
                 for sender, points in self.paths.items() if points]
        return sum(rates) / float(len(rates)) if rates else 0.0

    def _sender_rate(self, sender: str, points: set[Point]) -> float:
        ratios = []
        for receiver in self.paths:
            if receiver == sender:
                continue
            sent = self.transmitted.get((sender, receiver), set())
            ratios.append(min(1.0, float(len(sent & points)) / float(len(points))))
        return sum(ratios) / float(len(self.paths) - 1)


def evaluate_batch_results(
    runs: list[dict[str, Any]],
    optimal_costs: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Aggregate caller-supplied run metrics by strategy.

    This compatibility helper does not establish historical instance pairing
    or the article tables' denominators."""
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

    opt_gaps = _optimality_gaps(solved_runs, optimal_costs or {})
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


def _optimality_gaps(solved_runs: list[dict[str, Any]],
                     optimal_costs: dict[str, int]) -> list[float]:
    gaps = []
    for run in solved_runs:
        reference = optimal_costs.get(str(run.get("scenario_id", "")), 0)
        if reference > 0:
            actual = run.get("total_path_length", 0)
            gaps.append(float(actual - reference) / float(reference))
    return gaps
