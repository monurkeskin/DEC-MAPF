"""Small complete workflow examples composed from the production services."""
from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import Any

from mapf.application.artifacts import export_bundle, standalone_html, svg_snapshot
from mapf.application.experiments import ExperimentService, compile_experiment
from mapf.application.narratives import narrated_html, negotiation_story
from mapf.application.runs import RunRepository, atomic_write, encode
from mapf.application.studies import experiment_card
from mapf.conformance import check_run_bundle


def run_capsule(spec: dict[str, Any], output: Path) -> dict[str, Any]:
    """Freeze, execute, qualify and export a declared small capsule once.

    A capsule budget remains in its specification. Failure rows are kept and
    exported; this helper does not retry or select the successful denominator.
    """
    manifest = compile_experiment(spec)
    if len(manifest["trials"]) > 16 or manifest["budget"]["workers"] != 1 or manifest["budget"]["wall_seconds"] > 120:
        raise ValueError("Capsules are limited to 16 trials, one worker and 120 batch seconds; use batch for larger studies")
    output.mkdir(parents=True, exist_ok=False)
    atomic_write(output / "manifest.json", encode(manifest))
    repository = RunRepository(output / "workspace")
    service = ExperimentService(repository)
    start = time.monotonic()
    summary = service.execute(manifest)
    rows = service.rows(manifest["experiment_id"])
    atomic_write(output / "all-trials.json", encode(rows))
    card = experiment_card(manifest, rows)
    atomic_write(output / "experiment-card.json", encode(card))
    exports = []
    story_run = None
    for row in rows:
        if row["state"] != "completed":
            continue
        payload = repository.get_run(row["run_id"])
        if payload is None:
            raise ValueError("Completed capsule artifact is missing")
        bundle = export_bundle(payload)
        checked = check_run_bundle(bundle)
        folder = output / row["run_id"]
        folder.mkdir()
        atomic_write(folder / "bundle.json", encode(bundle))
        atomic_write(folder / "replay.html", standalone_html(payload).encode())
        if payload["frames"]:
            atomic_write(folder / "initial.svg", svg_snapshot(payload).encode())
        exports.append(checked)
        if story_run is None and any(e.get("event_type") == "NEGO_SESSION" and e.get("outcome") == "AGREED"
                                     for e in payload["result"].get("telemetry_events", [])):
            story_run = row["run_id"]
            atomic_write(output / "negotiation-story.json", encode(negotiation_story(payload)))
            atomic_write(output / "negotiation-story.html", narrated_html(payload).encode())
    receipt = {"schema_version": "capsule-1", "summary": summary, "bundle_checks": exports,
               "story_run_id": story_run, "elapsed_wall_seconds": time.monotonic() - start,
               "wall_scope": "planning excluded; supervision, validation and export included",
               "platform": platform.platform(), "machine": platform.machine(),
               "peak_rss_bytes": None, "rss_scope": "not measured by this helper",
               "output_bytes_before_receipt": sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
               "scope": "teaching-fixture execution; not a benchmark generalization"}
    atomic_write(output / "receipt.json", encode(receipt))
    print(json.dumps(receipt, indent=2))
    return receipt
