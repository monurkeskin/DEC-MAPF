"""Command Line Interface (CLI) for DEC-MAPF.

Provides commands for solving single instances, running batch benchmark suites,
launching the researcher dashboard, and running full verification checks.
"""

from __future__ import annotations

import argparse
import sys
import time

from mapf.core.models import (
    CommitmentType,
    SimulationConfig,
    SimulationSetting,
)
from mapf.core.movingai import generate_benchmark_map, generate_stern_scenario
from mapf.solvers.base import MAPFInstance
from mapf.solvers.registry import get_solver, list_solvers


def list_solvers_command(args: argparse.Namespace) -> int:
    """List all registered MAPF solvers in the ecosystem."""
    solvers = list_solvers()
    print("\n=======================================================")
    print("  DEC-MAPF: Registered Solvers")
    print("=======================================================\n")
    for name, meta in sorted(solvers.items()):
        kind = "Centralized" if meta["is_centralized"] else "Decentralized"
        print(f"  • {name:15} [{kind:13}] : {meta['description']}")
    print()
    return 0


def solve_command(args: argparse.Namespace) -> int:
    """Solve an ad-hoc MAPF scenario with the requested solver."""
    print("\n=======================================================")
    print("  DEC-MAPF: Instance Solver")
    print(
        f"  Solver: {args.solver} | Agents: {args.agents} | Grid: {args.grid}x{args.grid}"
    )
    print(
        f"  Setting: {args.setting} | Commitment: {args.commitment} | FoV: {args.fov}"
    )
    print(f"  Obstacle Density: {args.density * 100:.1f}% | Seed: {args.seed}")
    print("=======================================================\n")

    obstacles = generate_benchmark_map(
        width=args.grid,
        height=args.grid,
        obstacle_density=args.density,
        seed=args.seed,
    )

    min_dist = 2 if args.grid <= 16 else 4
    max_dist = 12 if args.grid <= 16 else 24
    try:
        pairs = generate_stern_scenario(
            width=args.grid,
            height=args.grid,
            obstacles=obstacles,
            num_agents=args.agents,
            min_dist=min_dist,
            max_dist=max_dist,
            seed=args.seed,
        )
    except ValueError as exc:
        print(f"Error generating scenario: {exc}", file=sys.stderr)
        return 1

    starts = {f"Agent_{i + 1:02d}": pairs[i][0] for i in range(args.agents)}
    goals = {f"Agent_{i + 1:02d}": pairs[i][1] for i in range(args.agents)}

    instance = MAPFInstance(
        starts=starts,
        goals=goals,
        grid_width=args.grid,
        grid_height=args.grid,
        obstacles=obstacles,
    )
    config = SimulationConfig(
        grid_width=args.grid,
        grid_height=args.grid,
        obstacles=obstacles,
        fov_size=args.fov,
        setting=SimulationSetting(args.setting),
        commitment_type=CommitmentType(args.commitment),
        initial_tokens=5,
        max_steps=args.max_steps,
        random_seed=args.seed,
        centralized_timeout_sec=args.timeout,
    )

    solver = get_solver(args.solver)
    t0 = time.perf_counter()
    solution = solver.solve(instance, config)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    print("Result:")
    print(f"  Success:                  {'YES' if solution.success else 'NO'}")
    print(
        f"  Solved Agents:            {len(solution.paths) if solution.success else solution.metrics.get('solved_count', 0)} / {args.agents}"
    )
    print(f"  Makespan:                 {solution.makespan}")
    print(f"  Sum of Costs:             {solution.sum_of_costs}")
    print(f"  Total Computation Time:   {duration_ms:.2f} ms")
    if not solution.is_centralized:
        print(
            f"  Negotiations Conducted:   {solution.metrics.get('negotiation_count', 0)}"
        )
        print(
            f"  Successful Negotiations:  {solution.metrics.get('successful_negotiations', 0)}"
        )
        print(
            f"  Information Sharing Rate: {solution.metrics.get('information_sharing_rate', 0.0) * 100:.1f}%"
        )
    print("=======================================================\n")
    return 0 if solution.success else 1


def dashboard_command(args: argparse.Namespace) -> int:
    """Launch the interactive web researcher dashboard."""
    import os
    from pathlib import Path

    import uvicorn

    from mapf.application.resources import ResourcePolicy

    if args.resource_policy:
        policy_path = Path(args.resource_policy).resolve()
        ResourcePolicy.model_validate_json(policy_path.read_text())
        os.environ["MAPF_RESOURCE_POLICY"] = str(policy_path)
    if args.workers is not None:
        if args.workers > 4 and not os.environ.get("MAPF_RESOURCE_POLICY"):
            raise ValueError("More than four workers requires --resource-policy")
        os.environ["MAPF_WORKERS"] = str(args.workers)

    print(
        f"\n[MAPF Dashboard] Starting web interface at http://{args.host}:{args.port} ..."
    )
    uvicorn.run("mapf.gui.app:app", host=args.host, port=args.port, reload=False)
    return 0


def diagnostics_command(args: argparse.Namespace) -> int:
    """Generate deep scientific diagnostics from discrete telemetry."""
    from pathlib import Path

    from mapf.analytics.diagnostics_report import generate_html_report
    from mapf.analytics.post_simulation import (
        analyze_rejection_reasons,
        compute_agent_wait_dynamics,
        compute_concession_curves,
        compute_spatial_hotspots,
        compute_token_inequality_gini,
        extract_keyframes,
        extract_manifest,
        load_events_as_polars,
    )

    events_file = Path(args.events)
    if not events_file.exists():
        print(f"Error: Telemetry file {events_file} does not exist.", file=sys.stderr)
        return 1

    run_id = events_file.stem.replace("_events", "").replace(".jsonl", "")
    output_html = (
        Path(args.output)
        if args.output
        else events_file.parent / f"{run_id}_diagnostics.html"
    )

    print(f"\n[Deep Diagnostics] Analyzing telemetry stream from: {events_file}")
    df = load_events_as_polars(events_file)
    print(f"  Loaded {len(df)} discrete events into Polars.")

    manifest = extract_manifest(df)
    hotspots = compute_spatial_hotspots(df, args.grid, args.grid)
    concessions = compute_concession_curves(df)
    gini_data = compute_token_inequality_gini(df)
    wait_data = compute_agent_wait_dynamics(df)
    rejection_data = analyze_rejection_reasons(df)
    keyframes = extract_keyframes(df)

    print("\n--- Summary Telemetry Insights ---")
    if manifest:
        print(
            f"  • Run Setting / Commit:        {manifest.get('setting')} / {manifest.get('git_commit')}"
        )
    print(f"  • Total Negotiation Conflicts: {hotspots['total_conflicts']}")
    print(
        f"  • Negotiation Success Rate:    {rejection_data['success_rate'] * 100:.1f}%"
    )
    print(f"  • Token Wealth Gini Index:     {gini_data['gini_coefficient']:.4f}")
    print(f"  • Mean Wait Ratio:             {wait_data['mean_wait_ratio'] * 100:.2f}%")
    print(f"  • Checkpoint Keyframes:        {len(keyframes)}")

    generate_html_report(
        run_id=run_id,
        manifest=manifest,
        hotspots=hotspots,
        concessions=concessions,
        gini_data=gini_data,
        wait_data=wait_data,
        rejection_data=rejection_data,
        keyframes=keyframes,
        grid_width=args.grid,
        grid_height=args.grid,
        output_html_path=output_html,
    )
    return 0


def verify_command(args: argparse.Namespace) -> int:
    """Run full automated verification suite (pytest, ruff, mypy)."""
    import subprocess

    print("\n--- 1. Running Ruff Linter ---")
    ret_ruff = subprocess.call([sys.executable, "-m", "ruff", "check", "src", "tests"])
    if ret_ruff != 0:
        return ret_ruff

    print("\n--- 2. Running Mypy Strict Type Checker ---")
    ret_mypy = subprocess.call([sys.executable, "-m", "mypy", "src"])
    if ret_mypy != 0:
        return ret_mypy

    print("\n--- 3. Running Pytest Suite ---")
    ret_pytest = subprocess.call([sys.executable, "-m", "pytest"])
    return ret_pytest


def workspace_plan_command(args: argparse.Namespace) -> int:
    """Write the same bounded effective-input preview used by the GUI; no execution."""
    import json
    from pathlib import Path

    from mapf.application.contracts import JobSubmissionRequest
    from mapf.application.plans import preview_batch
    from mapf.application.profiles import preview_profile

    if args.profile:
        result = preview_profile(args.profile)
    else:
        result = preview_batch(
            [
                JobSubmissionRequest.model_validate(j)
                for j in json.loads(Path(args.jobs).read_text())
            ]
        )
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mapf",
        description="DEC-MAPF: Discrete-Event Simulation, Benchmarking, and Diagnostics CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    from mapf.doctor_cli import register as register_doctor
    register_doctor(subparsers)
    from mapf.study_cli import register as register_study
    register_study(subparsers)

    available_solvers = sorted(list_solvers().keys())

    # Subcommand: solve
    p_solve = subparsers.add_parser("solve", help="Solve an ad-hoc MAPF scenario")
    p_solve.add_argument("--solver", choices=available_solvers, default="HeatMap")
    p_solve.add_argument("--agents", type=int, default=10, help="Number of agents (k)")
    p_solve.add_argument("--grid", type=int, default=16, help="Grid dimension (N x N)")
    p_solve.add_argument(
        "--density", type=float, default=0.0, help="Obstacle density (0.0 - 0.3)"
    )
    p_solve.add_argument(
        "--setting",
        type=int,
        choices=[1, 2, 3, 4],
        default=4,
        help="JAAMAS Setting (1-4)",
    )
    p_solve.add_argument(
        "--commitment",
        choices=["SC", "DC", "ZC"],
        default="SC",
        help="Commitment horizon",
    )
    p_solve.add_argument("--fov", type=int, default=5, help="Field of View size")
    p_solve.add_argument(
        "--max-steps", type=int, default=100, help="Max simulation steps"
    )
    p_solve.add_argument(
        "--timeout", type=float, default=60.0, help="Timeout in seconds"
    )
    p_solve.add_argument("--seed", type=int, default=42, help="Random seed")
    p_solve.set_defaults(func=solve_command)

    # Subcommand: solvers
    p_solvers = subparsers.add_parser(
        "solvers", help="List all registered solvers in the ecosystem"
    )
    p_solvers.set_defaults(func=list_solvers_command)

    # Subcommand: diagnostics
    p_diag = subparsers.add_parser(
        "diagnostics", help="Generate deep scientific diagnostics from telemetry"
    )
    p_diag.add_argument(
        "events", type=str, help="Path to events.jsonl.gz or events.jsonl"
    )
    p_diag.add_argument(
        "--grid", type=int, default=16, help="Grid dimension (default: 16)"
    )
    p_diag.add_argument(
        "--output", type=str, default=None, help="Output HTML file path"
    )
    p_diag.set_defaults(func=diagnostics_command)

    # Subcommand: dashboard
    p_dash = subparsers.add_parser(
        "dashboard", help="Launch interactive web researcher dashboard"
    )
    p_dash.add_argument("--host", default="127.0.0.1", help="Host interface")
    p_dash.add_argument("--port", type=int, default=8000, help="Port number")
    p_dash.add_argument("--workers", type=int, choices=range(1, 7), help="Owned solver processes (default 2)")
    p_dash.add_argument("--resource-policy", help="JSON resource-admission policy; requires resources extra")
    p_dash.set_defaults(func=dashboard_command)

    p_plan = subparsers.add_parser(
        "workspace-plan", help="Preview an exact local GUI/headless experiment manifest"
    )
    group = p_plan.add_mutually_exclusive_group(required=True)
    group.add_argument("--profile", choices=["smoke-v1", "settings-smoke-v1"])
    group.add_argument("--jobs", help="JSON list of job definitions")
    p_plan.add_argument("--output", help="Write preview manifest to this file")
    p_plan.set_defaults(func=workspace_plan_command)

    # Subcommand: verify
    p_ver = subparsers.add_parser(
        "verify", help="Run full test and static analysis suite"
    )
    p_ver.set_defaults(func=verify_command)

    from mapf.experiment_cli import register
    register(subparsers)
    args = parser.parse_args()
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
