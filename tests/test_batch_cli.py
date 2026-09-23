"""Batch CLI contracts use a real durable workspace and bounded two-trial run."""

import argparse
import csv
import json
import signal

import pytest

from mapf import experiment_cli, study_cli
from mapf.application.experiments import ExperimentService, compile_experiment
from mapf.application.runs import RunRepository


def invoke(argv):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(required=True)
    experiment_cli.register(commands)
    study_cli.register(commands)
    args = parser.parse_args([str(value) for value in argv])
    return args.func(args)


@pytest.fixture
def workspace(tmp_path):
    spec = {"name": "CLI acceptance", "scenarios": [{"scenario_id": "crossing-2a"}],
            "defaults": {"setting": "SETTING_4", "max_steps": 30, "timeout_sec": 10},
            "matrix": {"solver_id": ["CBS", "Decentralized-HeatMap"]},
            "budget": {"workers": 1, "wall_seconds": 30, "max_trials": 2, "disk_mb": 128}}
    manifest = compile_experiment(spec)
    folder = tmp_path / "workspace"
    ExperimentService(RunRepository(folder)).register(manifest)
    return folder, manifest, spec


def test_plan_run_status_resume_and_exports_share_the_frozen_inputs(workspace, tmp_path, capsys):
    folder, manifest, spec = workspace
    spec_file, manifest_file = tmp_path / "spec.json", tmp_path / "manifest.json"
    spec_file.write_text(json.dumps(spec))
    assert invoke(["batch", "plan", spec_file, "--output", manifest_file]) == 0
    assert json.loads(capsys.readouterr().out)["items"] == 2
    assert json.loads(manifest_file.read_text())["manifest_digest"] == manifest["manifest_digest"]
    assert invoke(["batch", "run", manifest_file, "--workspace", folder, "--resume"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"] == {"completed": 2}
    experiment = manifest["experiment_id"]
    assert invoke(["batch", "resume", experiment, "--workspace", folder, "--retry-failed"]) == 0
    assert json.loads(capsys.readouterr().out)["planned"] == 2
    rows_path = tmp_path / "all.csv"
    assert invoke(["batch", "export", experiment, "--workspace", folder, "--output", rows_path]) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == 2
    with rows_path.open() as stream:
        rows = list(csv.DictReader(stream))
    assert {row["trial_id"] for row in rows} == {trial["trial_id"] for trial in manifest["trials"]}
    assert invoke(["batch", "status", experiment, "--workspace", folder]) == 0
    assert json.loads(capsys.readouterr().out)["successful"] == 2


def test_read_only_commands_keep_pending_trials_and_do_not_admit_jobs(workspace, tmp_path, capsys):
    folder, manifest, _ = workspace
    experiment = manifest["experiment_id"]
    destination = tmp_path / "status.json"
    assert invoke(["batch", "status", "--workspace", folder, "--output", destination]) == 0
    assert json.loads(capsys.readouterr().out)["items"] == 1
    assert len(json.loads(destination.read_text())) == 1
    assert invoke(["batch", "export", experiment, "--workspace", folder, "--output", destination]) == 0
    capsys.readouterr()
    rows = json.loads(destination.read_text())
    assert len(rows) == 2 and {row["state"] for row in rows} == {"not_admitted"}
    argv = ["batch", "analyze", experiment, "--workspace", folder,
            "--left", "CBS", "--right", "Decentralized-HeatMap", "--filters", "{}"]
    assert invoke(argv) == 0
    assert json.loads(capsys.readouterr().out)["coverage"]["neither"] == 1
    figures = tmp_path / "figures"
    assert invoke([*argv, "--figures", figures]) == 0
    receipt = json.loads(capsys.readouterr().out)["export_receipt"]
    assert {"experiment-manifest.json", "all-planned-trials.json"} <= receipt["files"].keys()
    assert json.loads((figures / "all-planned-trials.json").read_text()) == rows
    assert RunRepository.open_existing(folder, read_only=True).list_jobs() == []


def test_study_scaffold_and_card_preserve_all_planned_denominators(workspace, tmp_path, capsys):
    folder, manifest, _ = workspace
    study = tmp_path / "study"
    assert invoke(["study", "init", study, "--name", "Independent study"]) == 0
    assert json.loads(capsys.readouterr().out)["executed"] is False
    assert (study / "run.py").is_file()
    assert invoke(["study", "init", study]) == 1
    assert "FileExistsError" in json.loads(capsys.readouterr().out)["error"]
    output = tmp_path / "card.json"
    assert invoke(["study", "card", manifest["experiment_id"], "--workspace", folder, "--output", output]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == json.loads(output.read_text())
    assert result["outcomes"]["planned"] == 2 and result["outcomes"]["valid_solutions"] == 0


@pytest.mark.parametrize("action", ["status", "analyze", "export", "resume"])
def test_missing_workspace_fails_without_creating_it(action, tmp_path, capsys):
    missing = tmp_path / "missing"
    argv = ["batch", action, "absent", "--workspace", missing]
    if action == "analyze":
        argv += ["--left", "CBS", "--right", "Decentralized-HeatMap"]
    previous = signal.getsignal(signal.SIGTERM)
    assert invoke(argv) == 1
    assert "error" in json.loads(capsys.readouterr().out)
    assert not missing.exists()
    assert signal.getsignal(signal.SIGTERM) == previous


@pytest.mark.parametrize("state", ["interrupted", "budget_exhausted", "resource_blocked", "failed"])
@pytest.mark.parametrize("write_output", [False, True], ids=["stdout", "file"])
def test_machine_exit_status_preserves_unsuccessful_experiment_state(workspace, tmp_path, capsys, state, write_output):
    folder, manifest, _ = workspace
    with RunRepository.open_existing(folder, read_only=False).connect() as database:
        database.execute("UPDATE experiments SET state=? WHERE id=?", (state, manifest["experiment_id"]))
    argv = ["batch", "status", manifest["experiment_id"], "--workspace", folder]
    if write_output:
        argv += ["--output", tmp_path / "summary.json"]
    assert invoke(argv) == 2
    payload = json.loads((tmp_path / "summary.json").read_text()) if write_output else json.loads(capsys.readouterr().out)
    assert payload["state"] == state


def test_sigterm_restores_callers_handler_when_planning_is_interrupted(tmp_path, monkeypatch):
    specification = tmp_path / "spec.json"
    specification.write_text("{}")
    def terminate(_spec):
        signal.raise_signal(signal.SIGTERM)
    monkeypatch.setattr(experiment_cli, "compile_experiment", terminate)
    previous = signal.getsignal(signal.SIGTERM)
    with pytest.raises(KeyboardInterrupt):
        invoke(["batch", "plan", specification])
    assert signal.getsignal(signal.SIGTERM) == previous


def test_legacy_csv_is_quarantined_without_claiming_current_pairing(tmp_path, capsys):
    source = tmp_path / "historical.csv"
    source.write_text("method,cost\nCBS,7\n")
    assert invoke(["batch", "import-legacy", source, "--destination", tmp_path / "archive",
                   "--source-type", "historical-empirical"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "quarantined" and not receipt["eligible_for_current_comparison"]
    assert receipt["sheets"][0]["rows"] == 1


@pytest.mark.parametrize("action", ["article-spec", "article-rosters"])
def test_article_commands_record_explicit_input_population_without_running(tmp_path, capsys, action):
    from mapf.core.models import Point
    from mapf.core.movingai import format_movingai_map, format_movingai_scen

    map_file, scenario = tmp_path / "empty.map", tmp_path / "ordered.scen"
    map_file.write_text(format_movingai_map(16, 16, set()))
    pairs = [(Point(i % 3, i // 3), Point(i % 3 + 7, i // 3)) for i in range(20)]
    scenario.write_text(format_movingai_scen(pairs, map_file.name, 16, 16))
    output = tmp_path / "article.json"
    argv = ["batch", action, "--map", map_file, "--scenarios", scenario,
            "--split", "held-out", "--workers", "1", "--wall-seconds", "60",
            "--timeout-sec", "600", "--output", output]
    argv += ["--agents", "20", "--fovs", "5"] if action == "article-spec" else ["--profile", "main-16"]
    assert invoke(argv) == 0
    assert json.loads(capsys.readouterr().out)["items"] == 1
    result = json.loads(output.read_text())
    assert result["sampling"]["split"] == "held-out"
    assert len(result["scenarios"][0]["starts"]) == 20
    assert result["defaults"]["timeout_sec"] == 600
