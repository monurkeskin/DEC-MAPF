"""External executables must satisfy their declared path and identity before use."""

import json

import pytest

from mapf.application.native_solvers import NativeSolverProfile, native_profiles
from tests import test_native_profiles

native = test_native_profiles.native


def test_relative_native_executable_is_rejected(native):
    with pytest.raises(ValueError, match="absolute"):
        NativeSolverProfile.model_validate({**native[2], "executable": "fixture.sh"})


@pytest.mark.parametrize("failure", ["missing", "not-executable"])
def test_unusable_native_binary_cannot_be_admitted(native, failure):
    binary, _, record = native
    profile = NativeSolverProfile.model_validate(record)
    if failure == "missing":
        binary.unlink()
    else:
        binary.chmod(0o644)
    with pytest.raises(ValueError, match="missing or not executable"):
        profile.verify_binary()


def test_catalog_size_limit_precedes_json_parsing(tmp_path, monkeypatch):
    catalog = tmp_path / "oversize.json"
    catalog.write_text(json.dumps({"padding": "x" * (2 * 1024 * 1024)}))
    monkeypatch.setenv("MAPF_NATIVE_SOLVER_CATALOG", str(catalog))
    with pytest.raises(ValueError, match="2 MiB"):
        native_profiles()
