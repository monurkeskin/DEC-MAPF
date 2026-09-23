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
    _check_budget(manifest)
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
    exports = _CapsuleExports(repository, output)
    exports.write(rows)
    receipt = {"schema_version": "capsule-1", "summary": summary, "bundle_checks": exports.checks,
               "story_run_id": exports.story_run, "elapsed_wall_seconds": time.monotonic() - start,
               "wall_scope": "planning excluded; supervision, validation and export included",
               "platform": platform.platform(), "machine": platform.machine(),
               "peak_rss_bytes": None, "rss_scope": "not measured by this helper",
               "output_bytes_before_receipt": sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
               "scope": "teaching-fixture execution; not a benchmark generalization"}
    atomic_write(output / "receipt.json", encode(receipt))
    print(json.dumps(receipt, indent=2))
    return receipt


def _check_budget(manifest: dict[str, Any]) -> None:
    budget = manifest["budget"]
    limits = (len(manifest["trials"]) <= 16, budget["workers"] == 1, budget["wall_seconds"] <= 120)
    if not all(limits):
        raise ValueError("Capsules are limited to 16 trials, one worker and 120 batch seconds; use batch for larger studies")


class _CapsuleExports:
    """Export completed attempts and select the first recorded agreement story."""

    def __init__(self, repository: RunRepository, output: Path) -> None:
        self.repository, self.output = repository, output
        self.checks: list[dict[str, Any]] = []
        self.story_run: str | None = None

    def write(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if row["state"] == "completed":
                self._export_run(row["run_id"])

    def _export_run(self, run_id: str) -> None:
        payload = self.repository.get_run(run_id)
        if payload is None:
            raise ValueError("Completed capsule artifact is missing")
        bundle = export_bundle(payload)
        checked = check_run_bundle(bundle)
        folder = self.output / run_id
        folder.mkdir()
        atomic_write(folder / "bundle.json", encode(bundle))
        atomic_write(folder / "replay.html", standalone_html(payload).encode())
        if payload["frames"]:
            atomic_write(folder / "initial.svg", svg_snapshot(payload).encode())
        self.checks.append(checked)
        self._export_story(run_id, payload)

    def _export_story(self, run_id: str, payload: dict[str, Any]) -> None:
        if self.story_run is not None:
            return
        if not any(_agreed(e) for e in payload["result"].get("telemetry_events", [])):
            return
        self.story_run = run_id
        atomic_write(self.output / "negotiation-story.json", encode(negotiation_story(payload)))
        atomic_write(self.output / "negotiation-story.html", narrated_html(payload).encode())


def _agreed(event: dict[str, Any]) -> bool:
    return event.get("event_type") == "NEGO_SESSION" and event.get("outcome") == "AGREED"
