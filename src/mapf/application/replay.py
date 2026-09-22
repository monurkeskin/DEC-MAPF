"""Frame builder and lifecycle contract manager for MAPF replay timeline.

Enforces:
1. One contract for t=0 initial state, t -> t+1 movement, and frame timestamps.
2. Four-state solution classification: solved, failed, truncated, invalid.
3. Visual agent lifecycle: active, reached, disappeared (under DaT), parked (under noDaT),
   and collided/deadlocked.
4. Separation of local observations, executed history, and spatial heat.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from mapf.application.contracts import (
    ConflictRecord,
    ContractRecord,
    FrameSnapshot,
    Point2D,
    SolverRunResult,
    ValidationReceipt,
)
from mapf.core.models import SimulationSetting
from mapf.core.solution_validator import validate_solution
from mapf.metrics.costs import trajectory_costs
from mapf.solvers.base import MAPFInstance, MAPFSolution


def build_solver_run_result(
    solver_name: str,
    solver_key: str,
    instance: MAPFInstance,
    solution: MAPFSolution,
    setting: SimulationSetting,
    fov_size: int,
    initial_tokens: int = 5,
    max_steps: int = 100,
    include_frames: bool = True,
) -> SolverRunResult:
    """Transform a MAPFSolution into a verified, frame-sequenced SolverRunResult."""
    # 1. Physical validation check
    val_result = validate_solution(instance, solution.paths, setting)
    no_complete_candidate = (
        solution.is_centralized
        and not solution.metrics.get("solver_reported_success", solution.success)
        and set(solution.paths) != set(instance.starts)
    )
    physical_errors = [e for e in val_result.errors if e.error_type != "wrong_goal"
                       and not (no_complete_candidate and e.error_type == "missing_path")]
    has_physical_violation = len(physical_errors) > 0

    # 2. Check goal arrival per agent
    all_at_goal = True
    arrival_ticks: dict[str, int | None] = {}
    for aid, goal in instance.goals.items():
        path = solution.paths.get(aid)
        arr_t: int | None = None
        if path and len(path.points) > 0:
            for idx, pt in enumerate(path.points):
                if pt.x == goal.x and pt.y == goal.y:
                    arr_t = idx
                    break
        arrival_ticks[aid] = arr_t
        if arr_t is None or (path and path.points[-1] != goal):
            all_at_goal = False

    # 3. Classify run status
    status: Literal["solved", "failed", "truncated", "invalid"]
    if has_physical_violation:
        status = "invalid"
        verified_success = False
    elif all_at_goal and val_result.is_valid and solution.success:
        status = "solved"
        verified_success = True
    elif solution.makespan >= max_steps:
        status = "truncated"
        verified_success = False
    else:
        status = "failed"
        verified_success = False

    # 4. Serialize paths
    serialized_paths: dict[str, list[Point2D]] = {}
    for aid, p in solution.paths.items():
        serialized_paths[aid] = [Point2D(x=pt.x, y=pt.y) for pt in p.points]

    # 5. Extract raw decentralized frames / events if present
    raw_frames = solution.metrics.get("frames", [])
    raw_frames_by_tick: dict[int, dict[str, Any]] = {}
    initial = solution.metrics.get("initial_snapshot", {})
    if initial:
        raw_frames_by_tick[0] = initial
    for f in raw_frames:
        f_dict = f.to_dict() if hasattr(f, "to_dict") else dict(f)
        raw_frames_by_tick[f_dict.get("tick", 0) + 1] = f_dict

    total_ticks = max((p.length for p in solution.paths.values()), default=0)
    frames: list[FrameSnapshot] = []

    # 6. Construct frames from t = 0 to t = total_ticks
    for t in range(total_ticks + 1 if include_frames else 0):
        positions: dict[str, list[int]] = {}
        targets: dict[str, list[int]] = {}
        statuses: dict[
            str,
            Literal[
                "active", "reached", "parked", "disappeared", "deadlocked", "collided"
            ],
        ] = {}
        tokens: dict[str, int] = {}

        raw_f = raw_frames_by_tick.get(t)
        raw_tokens = raw_f.get("tokens", {}) if raw_f else {}

        active_count = 0
        solved_count = 0

        for aid in instance.starts:
            goal = instance.goals[aid]
            targets[aid] = [goal.x, goal.y]
            if t == 0 and not solution.is_centralized:
                tokens[aid] = initial_tokens
            elif aid in raw_tokens:
                tokens[aid] = raw_tokens[aid]

            path = solution.paths.get(aid)
            if not path or len(path.points) == 0:
                pos = instance.starts[aid]
            else:
                pt_idx = min(t, len(path.points) - 1)
                pos = path.points[pt_idx]

            positions[aid] = [pos.x, pos.y]

            arr_t = arrival_ticks.get(aid)
            if arr_t is not None and t >= arr_t:
                solved_count += 1
                if setting.disappear_at_target:
                    if t == arr_t:
                        statuses[aid] = "reached"  # Goal reached on this tick
                    else:
                        statuses[aid] = "disappeared"  # Hidden on subsequent ticks
                else:
                    statuses[aid] = "parked"  # Static obstacle on grid
            else:
                active_count += 1
                statuses[aid] = "active"
            if any(
                e.error_type in ("vertex_collision", "edge_collision")
                and e.time_step == t
                and aid in (e.agent_a, e.agent_b)
                for e in physical_errors
            ):
                statuses[aid] = "collided"

        # Compute heat grid for active agents within upcoming window [t, t + fov_size]
        heat_grid: dict[str, float] = {}
        for aid, pts in serialized_paths.items():
            if statuses.get(aid) in ("disappeared", "parked"):
                continue
            subpath = pts[t : t + fov_size]
            for p2d in subpath:
                key = f"{p2d.x}-{p2d.y}"
                heat_grid[key] = heat_grid.get(key, 0.0) + 1.0

        conflicts: list[ConflictRecord] = []
        contracts: list[ContractRecord] = []
        if raw_f:
            for c in raw_f.get("conflicts", []):
                conflicts.append(
                    ConflictRecord(
                        a=c.get("a", ""),
                        b=c.get("b", ""),
                        time=c.get("time", t),
                        type=c.get("type", "vertex"),
                        location=c.get("location"),
                    )
                )
            for sc in raw_f.get("contracts", []):
                contracts.append(
                    ContractRecord(
                        agent_a=sc.get("agent_a", ""),
                        agent_b=sc.get("agent_b", ""),
                        location=sc.get("location"),
                        time=sc.get("time", t),
                        details=sc.get("details", {}),
                    )
                )

        frame = FrameSnapshot(
            tick=t,
            active_agents=active_count,
            solved_agents=solved_count,
            positions=positions,
            targets=targets,
            statuses=statuses,
            tokens=tokens,
            conflicts=conflicts,
            contracts=contracts,
            heat_grid=heat_grid,
            is_unsolvable=raw_f.get("is_unsolvable", False) if raw_f else False,
            phase="initial" if t == 0 else "post_move",
            telemetry_available=raw_f is not None,
            planned_paths=raw_f.get("planned_paths", {}) if raw_f else {},
            commitments=raw_f.get("commitments", {}) if raw_f else {},
            local_observations=raw_f.get("local_observations") if raw_f else None,
            local_heat=raw_f.get("local_heat", []) if raw_f else [],
            local_heat_omitted=raw_f.get("local_heat_omitted", 0) if raw_f else 0,
        )
        frames.append(frame)

    costs = trajectory_costs(instance, solution.paths)
    return SolverRunResult(
        solver=solution.solver_name,
        solver_key=solver_key,
        is_centralized=solution.is_centralized,
        status=status,
        success=verified_success,
        solved_count=len([a for a, arr in arrival_ticks.items() if arr is not None]),
        total_agents=len(instance.starts),
        makespan=costs["action_makespan"] if verified_success else total_ticks,
        reported_makespan=solution.metrics.get("solver_reported_makespan", solution.makespan),
        reported_sum_of_costs=solution.metrics.get("solver_reported_sum_of_costs", solution.sum_of_costs),
        solver_outcome="solved"
        if solution.metrics.get("solver_reported_success", solution.success)
        else "not_solved",
        validation=ValidationReceipt(
            status="invalid"
            if physical_errors
            else "not_checked"
            if no_complete_candidate
            else "valid_solution"
            if val_result.is_valid
            else "valid_prefix",
            is_valid=val_result.is_valid,
            prefix_valid=not physical_errors and not no_complete_candidate,
            errors=[asdict(e) for e in val_result.errors],
            first_violation_tick=min(
                (e.time_step or 0 for e in physical_errors), default=None
            ),
        ),
        metric_availability={
            k: k in solution.metrics
            for k in (
                "negotiation_count",
                "successful_negotiations",
                "information_sharing_rate",
                "norm_path_diff",
            )
        },
        sum_of_costs=costs["action_sum_of_costs"] if verified_success else costs["recorded_action_count"],
        runtime_ms=round(solution.runtime_ms, 2),
        negotiation_count=solution.metrics.get("negotiation_count", 0),
        successful_negotiations=solution.metrics.get("successful_negotiations", 0),
        information_sharing_rate=solution.metrics.get("information_sharing_rate", 0.0),
        norm_path_diff=solution.metrics.get("norm_path_diff", 0.0),
        instance_hash=solution.instance_hash,
        run_id=solution.run_id,
        paths=serialized_paths,
        frames=frames,
        measured_metrics={**costs, **solution.metrics.get("communication", {}),
                          **({"termination_reason": solution.metrics["termination_reason"]}
                             if "termination_reason" in solution.metrics else {}),
                          **({"negotiations_by_tick": {str(t): n for t, n in solution.metrics["nego_by_step"].items()},
                              "negotiation_count": solution.metrics["negotiation_count"],
                              "successful_negotiations": solution.metrics["successful_negotiations"]}
                             if "nego_by_step" in solution.metrics else {}),
                          **({"solver_diagnostics": solution.metrics["solver_diagnostics"]}
                             if "solver_diagnostics" in solution.metrics else {})},
    )
