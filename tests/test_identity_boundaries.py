"""Scenario identities are stable across ordering and explicit about settings."""

import importlib
from enum import Enum

from mapf.core.hashing import compute_instance_hash, compute_run_id
from mapf.core.models import Point, SimulationSetting
from mapf.solvers.base import MAPFInstance


def test_instance_properties_preserve_the_unspecified_setting():
    instance = MAPFInstance(
        starts={"a": Point(0, 0)}, goals={"a": Point(1, 0)}, grid_width=2, grid_height=1
    )
    assert instance.agent_count == 1
    assert instance.instance_hash == compute_instance_hash(instance)
    explicit = compute_instance_hash(instance, SimulationSetting.SETTING_4)
    assert explicit == compute_instance_hash(instance, "SETTING_4")
    assert explicit != instance.instance_hash
    changed = instance.model_copy(update={"goals": {"a": Point(0, 0)}})
    assert changed.instance_hash != instance.instance_hash


def test_legacy_run_identity_normalizes_enums_and_ignores_unsupported_values():
    class Policy(Enum):
        FINITE = 1

    assert compute_run_id("instance", "solver") == compute_run_id(
        "instance", "solver", {}
    )
    enum_id = compute_run_id(
        "instance", "solver", {"policy": Policy.FINITE, "unsupported": []}
    )
    assert enum_id == compute_run_id("instance", "solver", {"policy": "FINITE"})
    assert enum_id != compute_run_id("instance", "solver", {"policy": "OTHER"})
    assert compute_run_id("instance", "solver", git_commit="a") != compute_run_id(
        "instance", "solver", git_commit="b"
    )


def test_importing_module_entrypoint_does_not_parse_the_host_arguments(monkeypatch):
    monkeypatch.setattr("sys.argv", ["host-program", "--not-a-mapf-option"])
    importlib.import_module("mapf.__main__")
