"""Machine-readable batch commands; no optional GUI imports."""

from __future__ import annotations

import argparse
import csv
import io
import json
import signal
from pathlib import Path
from typing import Any

from mapf.application.experiments import ExperimentService, compile_experiment
from mapf.application.runs import RunRepository, atomic_write, encode


def run_command(args: argparse.Namespace) -> int:
    result: Any
    def interrupted(_signal: int, _frame: Any) -> None:
        raise KeyboardInterrupt
    previous_signal = signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.batch_action == "article-spec":
            from mapf.application.article_suite import article_spec
            result = article_spec(Path(args.map), [Path(p) for p in args.scenarios],
                                  agents=args.agents, fovs=args.fovs, workers=args.workers,
                                  wall_seconds=args.wall_seconds, timeout_sec=args.timeout_sec, split=args.split)
        elif args.batch_action == "article-rosters":
            from mapf.application.article_suite import archived_article_spec
            result = archived_article_spec(Path(args.map), [Path(p) for p in args.scenarios],
                                           profile=args.profile, workers=args.workers,
                                           wall_seconds=args.wall_seconds, timeout_sec=args.timeout_sec,
                                           split=args.split, max_steps=args.max_steps,
                                           repair_dimensions_from_map=args.repair_dimensions_from_map)
        elif args.batch_action == "import-legacy":
            from mapf.application.legacy import quarantine_table
            result = quarantine_table(Path(args.source), Path(args.destination), args.source_type)
        elif args.batch_action == "plan":
            result = compile_experiment(json.loads(Path(args.spec).read_text()))
        else:
            repository = (RunRepository(args.workspace) if args.batch_action == "run" else
                          RunRepository.open_existing(args.workspace, read_only=args.batch_action != "resume"))
            service = ExperimentService(repository)
            if args.batch_action == "run":
                result = service.execute(json.loads(Path(args.manifest).read_text()), resume=args.resume)
            elif args.batch_action == "resume":
                result = service.resume(args.experiment, retry_failed=args.retry_failed)
            elif args.batch_action == "status":
                result = service.summary(args.experiment) if args.experiment else service.manifests()
            elif args.batch_action == "analyze":
                from mapf.analytics.experiment import (
                    analyze_experiment,
                    export_analysis,
                )
                rows = service.rows(args.experiment)
                result = analyze_experiment(rows, args.left, args.right,
                                            filters=json.loads(args.filters))
                if args.figures:
                    folder = Path(args.figures)
                    folder.mkdir(parents=True, exist_ok=True)
                    atomic_write(folder / "experiment-manifest.json", encode(service.get_manifest(args.experiment)))
                    atomic_write(folder / "all-planned-trials.json", encode(rows))
                    result["export_receipt"] = export_analysis(result, folder)
            else:
                result = service.rows(args.experiment)
                if args.output and Path(args.output).suffix == ".csv":
                    stream = io.StringIO()
                    fields = sorted({key for row in result for key in row})
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    for row in result:
                        writer.writerow({key: json.dumps(value) if isinstance(value, (dict, list)) else value
                                         for key, value in row.items()})
                    atomic_write(Path(args.output), stream.getvalue().encode())
                    print(json.dumps({"output": args.output, "rows": len(result)}))
                    return 0
        if getattr(args, "output", None):
            atomic_write(Path(args.output), encode(result))
            print(json.dumps({"output": args.output, "experiment_id": result.get("experiment_id") if isinstance(result, dict) else None,
                              "items": len(result.get("trials") or result.get("scenarios") or []) if isinstance(result, dict) else len(result or [])}))
            return 2 if isinstance(result, dict) and result.get("state") in ("interrupted", "budget_exhausted", "resource_blocked", "failed") else 0
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if isinstance(result, dict) and result.get("state") in ("interrupted", "budget_exhausted", "resource_blocked", "failed") else 0
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_signal)


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("batch", help="Plan, run, resume and export headless experiments")
    commands = parser.add_subparsers(dest="batch_action", required=True)
    article = commands.add_parser("article-spec", help="Freeze article-configured inputs from explicit MovingAI files")
    article.add_argument("--map", required=True)
    article.add_argument("--scenarios", nargs="+", required=True)
    article.add_argument("--agents", nargs="+", type=int, default=[20, 40, 60, 80])
    article.add_argument("--fovs", nargs="+", type=int, default=[5, 7, 9])
    article.add_argument("--split", choices=["development", "held-out"], required=True)
    article.add_argument("--workers", type=int, default=2)
    article.add_argument("--wall-seconds", type=float, default=3600)
    article.add_argument("--timeout-sec", type=float, default=600)
    article.add_argument("--output", required=True)
    article.set_defaults(func=run_command)
    exact = commands.add_parser("article-rosters", help="Preserve complete rosters under the distinct main-16 / appendix-32 paper profiles")
    exact.add_argument("--profile", choices=["main-16", "appendix-32"], required=True)
    exact.add_argument("--map", required=True)
    exact.add_argument("--scenarios", nargs="+", required=True)
    exact.add_argument("--split", choices=["development", "held-out"], required=True)
    exact.add_argument("--workers", type=int, default=2)
    exact.add_argument("--wall-seconds", type=float, default=3600)
    exact.add_argument("--timeout-sec", type=float, default=None,
                       help="Optional whole-trial administrative cap; omitted: no such cap, 60 seconds per negotiation")
    exact.add_argument("--max-steps", type=int, default=10000)
    exact.add_argument("--repair-dimensions-from-map", action="store_true",
                       help="Explicitly replace stale scenario width/height metadata with verified map dimensions; retain a per-row receipt")
    exact.add_argument("--output", required=True)
    exact.set_defaults(func=run_command)
    archive = commands.add_parser("import-legacy", help="Archive and qualify CSV/Parquet/XLSX without inventing pairing")
    archive.add_argument("source")
    archive.add_argument("--destination", required=True)
    archive.add_argument("--source-type", choices=["historical-empirical", "digitized-reference", "synthetic-demo", "unknown"], required=True)
    archive.set_defaults(func=run_command)
    plan = commands.add_parser("plan", help="Freeze Cartesian inputs and resource budgets without execution")
    plan.add_argument("spec")
    plan.add_argument("--output")
    for action in ("run", "resume", "status", "export", "analyze"):
        cmd = commands.add_parser(action)
        cmd.add_argument("--workspace", required=True, help="Durable local journal/artifact directory")
        if action == "run":
            cmd.add_argument("manifest")
            cmd.add_argument("--resume", action="store_true")
        elif action == "status":
            cmd.add_argument("experiment", nargs="?")
        else:
            cmd.add_argument("experiment")
        if action == "resume":
            cmd.add_argument("--retry-failed", action="store_true", help="Create one new attempt for explicit failed/timeout/cancelled trials")
        if action == "analyze":
            cmd.add_argument("--left", required=True)
            cmd.add_argument("--right", required=True)
            cmd.add_argument("--filters", default="{}", help="JSON mapping fields to allowed values")
            cmd.add_argument("--figures", help="Directory for canonical JSON/CSV/LaTeX/SVG/PDF/PNG exports")
        cmd.add_argument("--output")
        cmd.set_defaults(func=run_command)
    plan.set_defaults(func=run_command)
