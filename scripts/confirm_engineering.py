"""Execute a frozen, bounded software confirmation set without selecting outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.plans import preview, provenance
from mapf.application.runs import digest
from mapf.application.worker import solve_plan


def canonical_sessions(value):
    """Preserve session equality/references while normalizing per-run UUID labels."""
    names = {}

    def visit(node):
        if isinstance(node, dict):
            return {
                key: names.setdefault(item, f"session-{len(names)}")
                if key in ("session_id", "contract_id") and isinstance(item, str)
                else visit(item)
                for key, item in node.items()
            }
        if isinstance(node, list):
            return [visit(item) for item in node]
        return node

    return visit(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    data = json.loads(args.fixtures.read_text())
    output = {
        "kind": data["purpose"],
        "fixture_sha256": hashlib.sha256(args.fixtures.read_bytes()).hexdigest(),
        "provenance": provenance(),
        "cases": [],
    }
    for spec in data["cases"]:
        result = solve_plan(preview(JobSubmissionRequest(**spec)))["result"]
        core = {
            key: result[key]
            for key in (
                "success",
                "paths",
                "validation",
                "measured_metrics",
                "negotiation_count",
            )
        }
        core["measured_metrics"]["solver_diagnostics"].pop("heat_recording", None)
        # Additive heat trace is intentionally absent from the old replay contract.
        core["frames"] = [
            {
                k: v
                for k, v in f.items()
                if k not in ("local_heat", "local_heat_omitted")
            }
            for f in result["frames"]
        ]
        row = {
            "name": spec["name"],
            "success": result["success"],
            "validation": result["validation"]["status"],
            "signature": digest(canonical_sessions(core)),
            "behavior": core,
        }
        output["cases"].append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "behavior"}), flush=True)
        args.output.write_text(json.dumps(output, indent=2) + "\n")
    if args.compare:
        reference = json.loads(args.compare.read_text())
        if output["fixture_sha256"] != reference["fixture_sha256"]:
            raise AssertionError("Confirmation specification drifted")
        if [(r["name"], r["signature"]) for r in output["cases"]] != [
            (r["name"], r["signature"]) for r in reference["cases"]
        ]:
            raise AssertionError(
                "Reference and candidate behaviors differ; receipts retained for investigation"
            )


if __name__ == "__main__":
    main()
