"""Thin CLI adapter for study creation and evidence cards."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mapf.application.experiments import ExperimentService
from mapf.application.runs import RunRepository, atomic_write, encode
from mapf.application.studies import create_study, experiment_card


def run_command(args: argparse.Namespace) -> int:
    try:
        if args.study_action == "init":
            result = create_study(Path(args.directory), name=args.name)
        else:
            service = ExperimentService(RunRepository.open_existing(args.workspace, read_only=True))
            result = experiment_card(service.get_manifest(args.experiment), service.rows(args.experiment))
        if getattr(args, "output", None):
            atomic_write(Path(args.output), encode(result))
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        return 1


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("study", help="Create a study or export its evidence card")
    commands = parser.add_subparsers(dest="study_action", required=True)
    init = commands.add_parser("init", help="Create a new bounded teaching study; never overwrite")
    init.add_argument("directory")
    init.add_argument("--name", default="My first DEC-MAPF study")
    init.set_defaults(func=run_command)
    card = commands.add_parser("card", help="Read actual experiment metadata without running solvers")
    card.add_argument("experiment")
    card.add_argument("--workspace", required=True)
    card.add_argument("--output")
    card.set_defaults(func=run_command)
