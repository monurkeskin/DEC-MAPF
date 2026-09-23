"""Run the adjacent bounded capsule using an installed DEC-MAPF package."""
import argparse
import json
from pathlib import Path

from mapf.application.capsules import run_capsule

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = run_capsule(json.loads(Path(__file__).with_name("study.json").read_text()), args.output)
    summary = receipt["summary"]
    raise SystemExit(0 if summary["state"] == "completed" and summary["successful"] == summary["planned"] else 2)
