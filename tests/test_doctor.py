"""Installed-workflow diagnostics are read-only and optional-dependency aware."""
import json
import subprocess
import sys

from mapf.application.diagnostics import diagnose
from mapf.application.runs import RunRepository


def test_optional_components_are_not_required_for_core(monkeypatch):
    monkeypatch.setattr("mapf.application.diagnostics.module_available", lambda name: name in {"pydantic", "rfc8785"})
    assert diagnose()["status"] == "ok"
    report = diagnose(required=["gui"])
    assert report["status"] == "error"
    assert "gui" in report["missing_requirements"]


def test_missing_workspace_is_not_created(tmp_path):
    path = tmp_path / "missing"
    report = diagnose(workspace=path)
    assert report["status"] == "error" and "does not exist" in report["workspace"]["error"]
    assert not path.exists()


def test_doctor_inspects_existing_workspace_without_owning_or_migrating_it(tmp_path):
    repository = RunRepository(tmp_path)
    with repository.connect() as db:
        db.execute("PRAGMA user_version=0")
    report = diagnose(workspace=tmp_path)
    assert report["status"] == "ok"
    assert report["workspace"]["schema_version"] == 0
    assert report["workspace"]["jobs"] == report["workspace"]["runs"] == 0
    assert not (tmp_path / "supervisor.lock").exists()
    with repository.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 0


def test_doctor_cli_emits_machine_readable_failure(tmp_path):
    result = subprocess.run([sys.executable, "-m", "mapf.cli", "doctor", "--workspace", str(tmp_path / "missing")],
                            text=True, capture_output=True, timeout=20, check=False)
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "error"
