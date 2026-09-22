"""Frozen native identity and headless execution; fixtures are not real solvers."""

import hashlib
import json

import pytest

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.plans import preview
from mapf.application.solvers import SolverRegistry
from mapf.application.worker import solve_plan


@pytest.fixture
def native(tmp_path, monkeypatch):
    binary = tmp_path / "fixture.sh"
    binary.write_text("""#!/bin/sh
for arg in "$@"; do
  if [ "$prev" = --outputPaths ]; then out="$arg"; fi
  prev="$arg"
done
printf 'Agent 0: (0,0)->(0,1)\\n' > "$out"
""")
    binary.chmod(0o755)
    record = {
        "solver_id": "Native-fixture-S2",
        "display_name": "Fixture (unqualified)",
        "family": "eecbs",
        "setting": "SETTING_2",
        "executable": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "coordinate_order": "row-col",
        "source_revision": "synthetic fixture",
        "qualification_scope": "unqualified invocation fixture",
    }
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({"schema_version": "native-solvers-1", "profiles": [record]})
    )
    monkeypatch.setenv("MAPF_NATIVE_SOLVER_CATALOG", str(catalog))
    return binary, catalog, record


def request(**overrides):
    return JobSubmissionRequest(
        solver_id="Native-fixture-S2",
        grid_width=2,
        grid_height=2,
        starts={"a": [0, 0]},
        goals={"a": [1, 0]},
        setting=overrides.get("setting", "SETTING_2"),
        timeout_sec=5,
    )


def test_registered_native_profile_runs_headlessly_after_catalog_removed(
    native, monkeypatch
):
    plan = preview(request())
    assert (
        plan["effective_config"]["native_profile"]["binary_sha256"]
        == native[2]["binary_sha256"]
    )
    monkeypatch.delenv("MAPF_NATIVE_SOLVER_CATALOG")
    result = solve_plan(plan)["result"]
    assert result["success"] and result["sum_of_costs"] == 1
    assert (
        result["measured_metrics"]["solver_diagnostics"]["binary_sha256"]
        == native[2]["binary_sha256"]
    )


def test_modified_binary_cannot_execute_under_frozen_identity(native):
    plan = preview(request())
    native[0].write_text(native[0].read_text() + "# changed executable\n")
    with pytest.raises(ValueError, match="identity changed"):
        solve_plan(plan)
    with pytest.raises(ValueError, match="identity changed"):
        preview(request())


def test_new_binary_identity_changes_definition_digest(native):
    first = preview(request())
    binary, catalog, record = native
    binary.write_text(binary.read_text() + "# second revision\n")
    record["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    catalog.write_text(
        json.dumps({"schema_version": "native-solvers-1", "profiles": [record]})
    )
    second = preview(request())
    assert first["definition_digest"] != second["definition_digest"]


def test_wrong_setting_is_rejected_before_admission(native):
    with pytest.raises(ValueError, match="SETTING_2"):
        preview(request(setting="SETTING_1"))


def test_ambiguous_catalog_ids_are_rejected(native):
    _, catalog, record = native
    catalog.write_text(
        json.dumps({"schema_version": "native-solvers-1", "profiles": [record, record]})
    )
    with pytest.raises(ValueError, match="Duplicate"):
        SolverRegistry.list_capabilities()


def test_frozen_profile_cannot_be_redirected_by_solver_id(native):
    plan = preview(request())
    plan["effective_config"]["solver_id"] = "CBS"
    with pytest.raises(ValueError, match="profile.*solver"):
        solve_plan(plan)
