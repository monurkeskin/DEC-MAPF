"""Generate/check the researcher-facing parameter reference from actual schemas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.experiments import ExperimentBudget
from mapf.application.resources import ResourcePolicy

TARGET = Path(__file__).resolve().parents[1] / "docs" / "PARAMETERS.md"


def shape(schema: dict[str, Any]) -> str:
    if "anyOf" in schema:
        return " or ".join(shape(item) for item in schema["anyOf"])
    if "enum" in schema:
        return ", ".join(f"`{value}`" for value in schema["enum"])
    kind = schema.get("type", "object")
    bounds = []
    for key, label in (("minimum", "min"), ("maximum", "max"),
                       ("maxLength", "max characters"), ("maxItems", "max items"),
                       ("minItems", "min items")):
        if key in schema:
            bounds.append(f"{label} {schema[key]}")
    return kind + ("; " + ", ".join(bounds) if bounds else "")


def table(model: Any) -> str:
    schema = model.model_json_schema()
    rows = ["| Field | Default | Schema constraint |", "| --- | --- | --- |"]
    for name, field in schema["properties"].items():
        default = field.get("default", "empty collection" if name in ("starts", "goals", "obstacles") else "required")
        value = json.dumps(default, ensure_ascii=False)
        rows.append(f"| `{name}` | `{value}` | {shape(field)} |")
    return "\n".join(rows)


def render() -> str:
    return f"""# Parameters and effective inputs

[Documentation index](README.md) · [Scientific interpretation](SCIENCE.md) · [Experiment reference](EXPERIMENTS.md)

This table is generated from `JobSubmissionRequest` and `ExperimentBudget` in the current source. Regenerate with `uv run --no-sync python scripts/documentation_reference.py`; check drift with `--check`. These are application/API defaults, not an article protocol or the defaults of the separate direct `mapf solve` command.

## One job or one expanded matrix trial

{table(JobSubmissionRequest)}

Scenario dictionaries use integer `[x, y]` coordinates. Starts/goals need the same IDs and at least one agent; semantic validation follows schema validation. A built-in or workspace-owned `scenario_id` resolves a snapshot; portable external batches should carry inline coordinates. Grid shape, starts, goals, obstacles and name are scenario data, not solver parameters.

FoV is an **odd square width** (3, 5, 7, 9, 11, 13 or 15); the radius is floor(width/2). Null temporal horizons are resolved to the FoV width in the effective plan. Those horizons count states, including the current position; they are not distances or seconds. The interactive GUI form caps `max_steps` at 500; the application/headless schema permits up to 10,000.

`timeout_sec: null` is accepted only for decentralized jobs. Centralized jobs require a number. The bilateral deadline resets for a new session, never for an offer. In TAOP v2 the round limit is a diagnostic checkpoint, not a hard terminal offer count. Heat values are recorded only for applicable full-trace HeatMap decisions, bounded by the declared value budget and internal record-count guard.

`suboptimality` is active only for solvers/profiles that support it. It is not a general guarantee for a solver with a familiar name. Native catalogs also constrain the setting and freeze executable provenance. Preview reports canonical solver identity and `inactive_parameters`; consult `/api/v1/capabilities` for controls supported by your installed catalog.

## Whole experiment

{table(ExperimentBudget)}

The product of scenario count and matrix-axis lengths is checked against `max_trials` before exclusions. Fixed admission allows up to four workers; an explicit `resources` policy allows up to six. The GUI defaults to two workers and accepts an explicit `--workers` / `--resource-policy` configuration. Its experiment worker/policy settings must match the owning supervisor; the queue contains at most 32 pending/active jobs. Numerical-library thread caps are one per worker; they are not an OS memory guarantee.

Wall time is charged across resume. Disk limits stop work/admission when exhausted; do not treat them as a promise about the eventual compressed artifact size. The default interactive repository quota is 512 MiB; the batch runner applies its declared experiment disk budget. A GUI experiment must fit its existing workspace quota.

## Optional resource policy

{table(ResourcePolicy)}

Set `budget.resources` to opt in; null retains fixed admission. These are admission estimates and thresholds, not solver limits or OS memory guarantees. See [resource-aware batches](RESOURCE-ADMISSION.md) for blocked-state, resume and GUI policy semantics.

## Recording choice

| Level | Retained evidence | Intended use |
| --- | --- | --- |
| `metrics-only` | Paths, validation, measured counters, run/configuration provenance; no detailed replay frames/events/local heat | Broad batches and compact outcome analysis |
| `events` | Replay frames and recorded telemetry events; no full local decision/heat payloads | Movement and event inspection |
| `full-trace` | Available local observations, plans, commitments and applicable heat records, plus replay/events | Detailed explanations and debugging |

Recording limits and omissions are explicit. No later export can recreate a local decision that was never recorded. Replay is a visual artifact, not an exact-resume solver checkpoint.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != expected:
            raise SystemExit("Parameter documentation differs from current request schemas; regenerate it.")
        print("Parameter documentation matches current request schemas.")
    else:
        TARGET.write_text(expected)
        print(TARGET.name)


if __name__ == "__main__":
    main()
