"""Malformed native outputs must produce reviewable qualification failures."""

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def qualification():
    return runpy.run_path("scripts/native/qualify_native.py")


@pytest.fixture
def case():
    return {
        "width": 2,
        "height": 2,
        "starts": [(0, 0), (0, 1)],
        "goals": [(1, 0), (1, 1)],
        "obstacles": [],
    }


@pytest.mark.parametrize("setting", [1, 2, 3, 4])
def test_empty_path_is_an_endpoint_failure_not_a_validator_crash(
    qualification, case, setting
):
    errors = qualification["validate"](case, {0: [], 1: [(0, 1), (1, 1)]}, setting)
    assert errors == ["endpoints"]


def test_empty_native_csv_preserves_execution_receipt(qualification, case, monkeypatch):
    def native_output(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_text("")
        return SimpleNamespace(returncode=2, stdout="", stderr="native failure")

    monkeypatch.setattr(qualification["subprocess"], "run", native_output)
    result = qualification["execute"](
        {"executable": "fixture", "family": "eecbs"}, case, 1.1
    )
    assert result == {
        "exit": 2,
        "paths": {},
        "stdout": "",
        "stderr": "native failure",
        "stats": {},
    }
