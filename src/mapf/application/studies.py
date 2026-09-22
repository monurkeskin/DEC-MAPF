"""Study scaffolds and evidence cards; no solver or GUI implementation here."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from mapf.application.experiments import ExperimentSpec, verify_manifest
from mapf.application.runs import encode


def study_spec(name: str) -> dict[str, Any]:
    """A bounded teaching comparison, explicitly separate from article protocols."""
    return ExperimentSpec.model_validate({
        "name": name, "preset_id": "interactive-v1",
        "scenarios": [{"scenario_id": "crossing-2a"}, {"scenario_id": "grid-8x8-4a"}],
        "defaults": {"fov_size": 5, "initial_tokens": 5, "max_steps": 40},
        "matrix": {"solver_id": ["Decentralized-HeatMap", "Decentralized-PathAware"]},
        "budget": {"workers": 1, "wall_seconds": 120, "max_trials": 4, "disk_mb": 256},
        "sampling": {"population": "two declared teaching fixtures", "independent_unit": "scenario geometry and roster",
                     "generalization": "none; teaching fixtures only"},
    }).model_dump(exclude_none=True)


RUN_SCRIPT = '''"""Run this bounded study once; preserve outputs instead of overwriting them."""
import json
from pathlib import Path
from mapf.api import ExperimentService, RunRepository, compile_experiment

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    output = root / "outputs"
    output.mkdir(exist_ok=False)
    manifest = compile_experiment(json.loads((root / "study.json").read_text()))
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\\n")
    service = ExperimentService(RunRepository(output / "workspace"))
    summary = service.execute(manifest)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\\n")
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["state"] == "completed" else 2)
'''
ANALYZE_SCRIPT = '''"""Export all planned outcomes and an evidence card without starting any solver."""
import json
from pathlib import Path
from mapf.api import ExperimentService, RunRepository, experiment_card

if __name__ == "__main__":
    output = Path(__file__).resolve().parent / "outputs"
    manifest = json.loads((output / "manifest.json").read_text())
    service = ExperimentService(RunRepository.open_existing(output / "workspace", read_only=True))
    rows = service.rows(manifest["experiment_id"])
    (output / "all-trials.json").write_text(json.dumps(rows, indent=2) + "\\n")
    card = experiment_card(manifest, rows)
    (output / "experiment-card.json").write_text(json.dumps(card, indent=2) + "\\n")
    print(json.dumps(card, indent=2))
'''


def create_study(directory: Path, *, name: str = "My first DEC-MAPF study") -> dict[str, Any]:
    """Reserve a new directory atomically; existing paths/symlinks are never reused.

    Validation precedes filesystem writes. An I/O failure leaves the owned partial
    directory for inspection, never deletes a researcher's subsequently added file.
    """
    spec = study_spec(name)
    directory = directory.absolute()
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "maps").mkdir()
    files = {
        "study.json": encode(spec), "run.py": RUN_SCRIPT.encode(), "analyze.py": ANALYZE_SCRIPT.encode(),
        ".gitignore": b"outputs/\n__pycache__/\n",
        "maps/README.md": b"# Your maps\n\nPlace explicitly licensed MovingAI files here. The starter uses built-in fixtures. Import your files into study.json with `mapf batch article-spec` or the scenario API; record the input hashes and sampling population.\n",
        "README.md": f"""# {name}

Run a four-trial teaching study without a GUI. This is a software walkthrough,
not an article reproduction or a generalizable method comparison.

1. Edit `study.json` before running. Its budgets cap workers, time and storage.
2. With DEC-MAPF installed, run `python run.py`, then `python analyze.py`.
3. Inspect `outputs/experiment-card.json` and **all** `outputs/all-trials.json` rows.

The manifest freezes effective inputs, source identity and the full denominator.
A completed job can contain an unsolved valid prefix. Timeouts remain outcomes.
The study refuses an existing outputs directory. To resume an interrupted study,
use `mapf batch resume EXPERIMENT_ID --workspace outputs/workspace` with the ID in
`outputs/manifest.json`; failed-trial retries require an explicit separate choice.

Next: replace the teaching fixtures with your scenario population, state the
independent sampling unit, and retain the frozen manifest with every export.
See https://github.com/monurkeskin/DEC-MAPF/blob/main/docs/HEADLESS.md .
""".encode(),
    }
    for name_in_directory, content in files.items():
        with (directory / name_in_directory).open("xb") as stream:
            stream.write(content)
    return {"directory": str(directory.resolve()), "files": sorted(files), "executed": False}


def experiment_card(manifest: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe actual metadata with every planned row; never invent missing evidence."""
    verify_manifest(manifest, check_source=False)
    expected = {t["trial_id"] for t in manifest["trials"]}
    if len(rows) != len(expected) or {r["trial_id"] for r in rows} != expected:
        raise ValueError("Experiment card requires exactly every planned trial once")
    for row in rows:
        if row["experiment_id"] != manifest["experiment_id"] or row["source_sha256"] != manifest["source_sha256"]:
            raise ValueError("Trial provenance differs from the frozen experiment")
        if row["success"] and (row["state"] != "completed" or row["validation_status"] != "valid_solution"):
            raise ValueError("Success requires a completed independently valid solution")
    valid = sum(bool(r["success"]) for r in rows)
    return {"schema_version": "experiment-card-1", "name": manifest["name"],
            "experiment_id": manifest["experiment_id"], "manifest_digest": manifest["manifest_digest"],
            "provenance": manifest["provenance"], "sampling": manifest["sampling"], "budget": manifest["budget"],
            "methods": sorted({t["plan"]["effective_config"]["solver_id"] for t in manifest["trials"]}),
            "metric_versions": sorted({t["plan"]["provenance"]["metric_version"] for t in manifest["trials"]}),
            "outcomes": {"planned": len(rows), "states": dict(Counter(r["state"] for r in rows)),
                         "valid_solutions": valid, "success_rate": valid / len(rows),
                         "denominator": "all planned trials, including pending and unsuccessful outcomes"},
            "hardware": None, "paper_reproduction": "not established by this card",
            "citation": {"software": "Cite the package version and source identity above; see CITATION.cff",
                         "reference_paper_doi": "10.1007/s10458-024-09639-8"}}
