"""CLI contracts at user boundaries, without starting another server or test suite."""

import json
import os
import subprocess
import sys

import pytest

from mapf import cli
from mapf.application.resources import ResourcePolicy


def invoke(monkeypatch, *arguments):
    monkeypatch.setattr(sys, "argv", ["mapf", *arguments])
    with pytest.raises(SystemExit) as exited:
        cli.main()
    return exited.value.code


def test_solver_listing_distinguishes_registered_families(monkeypatch, capsys):
    assert invoke(monkeypatch, "solvers") == 0
    output = capsys.readouterr().out
    assert "CBS" in output and "Centralized" in output
    assert "HeatMap" in output and "Decentralized" in output


@pytest.mark.parametrize(("arguments", "exit_code", "message"), [
    (["--solver", "CBS", "--agents", "2", "--grid", "8"], 0, "Success:                  YES"),
    (["--solver", "HeatMap", "--agents", "2", "--grid", "8", "--max-steps", "1"], 1, "Success:                  NO"),
    (["--agents", "3", "--grid", "1"], 1, "Error generating scenario"),
])
def test_solve_exit_status_matches_delivered_outcome(monkeypatch, capsys, arguments, exit_code, message):
    assert invoke(monkeypatch, "solve", *arguments) == exit_code
    output = capsys.readouterr()
    assert message in output.out + output.err


@pytest.mark.parametrize("configured", ["defaults", "workers", "resources"])
def test_dashboard_launch_preserves_explicit_host_worker_and_resource_settings(tmp_path, monkeypatch, configured):
    import uvicorn

    monkeypatch.setenv("MAPF_WORKERS", "")
    monkeypatch.setenv("MAPF_RESOURCE_POLICY", "")
    launches = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **settings: launches.append((app, settings)))
    arguments = ["dashboard", "--host", "127.0.0.1", "--port", "8769"]
    if configured == "workers":
        arguments.extend(["--workers", "2"])
    if configured == "resources":
        policy = tmp_path / "resources.json"
        policy.write_text(ResourcePolicy().model_dump_json())
        arguments.extend(["--workers", "6", "--resource-policy", str(policy)])
    assert invoke(monkeypatch, *arguments) == 0
    assert launches == [("mapf.gui.app:app", {"host": "127.0.0.1", "port": 8769, "reload": False})]
    assert os.environ["MAPF_WORKERS"] == {"defaults": "", "workers": "2", "resources": "6"}[configured]
    if configured == "resources":
        assert os.environ["MAPF_RESOURCE_POLICY"] == str(policy.resolve())


def test_dashboard_rejects_extra_workers_without_resource_policy(monkeypatch):
    monkeypatch.setenv("MAPF_RESOURCE_POLICY", "")
    monkeypatch.setattr(sys, "argv", ["mapf", "dashboard", "--workers", "6"])
    with pytest.raises(ValueError, match="resource-policy"):
        cli.main()


@pytest.mark.parametrize(("return_codes", "expected"), [([2], 2), ([0, 3], 3), ([0, 0, 4], 4), ([0, 0, 0], 0)])
def test_verify_stops_at_first_failed_tool_and_uses_current_interpreter(monkeypatch, return_codes, expected):
    results = iter(return_codes)
    commands = []

    def check(command):
        commands.append(command)
        return next(results)

    monkeypatch.setattr(subprocess, "call", check)
    assert invoke(monkeypatch, "verify") == expected
    assert len(commands) == len(return_codes)
    assert [command[:3] for command in commands] == [
        [sys.executable, "-m", tool] for tool in ["ruff", "mypy", "pytest"][:len(return_codes)]]


@pytest.mark.parametrize("manifest", [False, True], ids=["legacy-without-manifest", "manifest"])
def test_diagnostics_produces_readable_html_from_real_event_file(tmp_path, monkeypatch, capsys, manifest):
    path = tmp_path / "tiny_events.jsonl"
    events = [{"event_type": "MOVE", "agent_id": "a", "tick": 1, "x": 1, "y": 0, "is_waiting": False}]
    if manifest:
        events.insert(0, {"event_type": "MANIFEST", "setting": "SETTING_4", "git_commit": "fixture"})
    path.write_text("\n".join(json.dumps(event) for event in events))
    assert invoke(monkeypatch, "diagnostics", str(path), "--grid", "4") == 0
    report = (tmp_path / "tiny_diagnostics.html").read_text()
    assert "tiny" in report
    assert "<html" in report.lower()
    assert "Summary Telemetry Insights" in capsys.readouterr().out


def test_diagnostics_missing_input_returns_failure_without_creating_report(tmp_path, monkeypatch, capsys):
    assert invoke(monkeypatch, "diagnostics", str(tmp_path / "missing.jsonl")) == 1
    assert "does not exist" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("source", ["profile", "jobs"])
def test_workspace_preview_has_same_json_on_stdout_and_disk(tmp_path, monkeypatch, capsys, source):
    arguments = ["workspace-plan", "--profile", "smoke-v1"]
    if source == "jobs":
        jobs = tmp_path / "jobs.json"
        jobs.write_text(json.dumps([{"scenario_id": "crossing-2a", "solver_id": "CBS"}]))
        arguments = ["workspace-plan", "--jobs", str(jobs)]
    assert invoke(monkeypatch, *arguments) == 0
    stdout = json.loads(capsys.readouterr().out)
    output = tmp_path / "plan.json"
    assert invoke(monkeypatch, *arguments, "--output", str(output)) == 0
    saved = json.loads(output.read_text())
    assert saved == stdout
    assert saved["plan_digest"]
