"""CLI adapter for read-only environment diagnostics."""
from __future__ import annotations

import argparse
import json
from typing import Any

from mapf.application.diagnostics import COMPONENTS, diagnose


def run_command(args: argparse.Namespace) -> int:
    result = diagnose(workspace=args.workspace, required=args.require)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("doctor", help="Check installed features and existing workspace without running jobs")
    parser.add_argument("--workspace", help="Existing workspace to inspect read-only")
    parser.add_argument("--require", action="append", choices=[*COMPONENTS, "native"], default=[],
                        help="Require an optional component; repeat for multiple components")
    parser.set_defaults(func=run_command)
