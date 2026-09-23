"""Capability discovery stays current without regenerating a schema per field."""

from dataclasses import asdict

import pytest

from mapf.application import solvers
from mapf.application.contracts import JobSubmissionRequest
from mapf.solvers import registry


@pytest.mark.parametrize("solver_id", [None, "Decentralized-HeatMap", "CBS"])
def test_one_schema_generation_per_capability_query(monkeypatch, solver_id):
    generate = JobSubmissionRequest.model_json_schema
    calls = []

    def schema():
        calls.append(1)
        return generate()

    monkeypatch.setattr(JobSubmissionRequest, "model_json_schema", schema)
    if solver_id is None:
        assert solvers.SolverRegistry.list_capabilities()
    else:
        assert solvers.SolverRegistry.get_capability(solver_id).solver_id == solver_id
    assert len(calls) == 1


def test_single_solver_query_does_not_describe_other_solvers(monkeypatch):
    metadata = solvers.solver_metadata
    described = []

    def selected(name):
        described.append(name)
        return metadata(name)

    monkeypatch.setattr(solvers, "solver_metadata", selected)
    assert solvers.SolverRegistry.get_capability("cbs").solver_id == "CBS"
    assert described == ["CBS"]


def test_capabilities_remain_isolated_and_follow_current_contract(monkeypatch):
    generate = JobSubmissionRequest.model_json_schema
    original = solvers.SolverRegistry.get_capability("HeatMap")

    def revised_schema():
        schema = generate()
        schema["properties"]["initial_tokens"]["default"] = 17
        return schema

    monkeypatch.setattr(JobSubmissionRequest, "model_json_schema", revised_schema)
    current = {c.solver_id: c for c in solvers.SolverRegistry.list_capabilities()}
    heatmap = {p.name: p for p in current["Decentralized-HeatMap"].parameters}
    path_aware = {p.name: p for p in current["Decentralized-PathAware"].parameters}
    expected = JobSubmissionRequest.model_fields["initial_tokens"].default
    assert next(p.default for p in original.parameters if p.name == "initial_tokens") == expected
    assert heatmap["initial_tokens"].default == path_aware["initial_tokens"].default == 17
    heatmap["commitment_type"].options.clear()
    assert path_aware["commitment_type"].options == ["SC", "DC", "ZC"]
    assert solvers.parameter_descriptor("commitment_type").options == ["SC", "DC", "ZC"]


@pytest.mark.parametrize("name", ["HeatMap", "heatmap", "Decentralized-HeatMap", "cbs", "EECBS"])
def test_selected_descriptor_matches_the_complete_catalog(name):
    cap = solvers.SolverRegistry.get_capability(name)
    catalog = {c.solver_id: asdict(c) for c in solvers.SolverRegistry.list_capabilities()}
    assert asdict(cap) == catalog[cap.solver_id]


def test_discovery_observes_solver_registration_after_previous_queries(monkeypatch):
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))
    before = {c.solver_id for c in solvers.SolverRegistry.list_capabilities()}
    name = "CapabilityFixture"
    assert name not in before
    registry.register_solver(name, is_centralized=True, description="Fixture metadata")(
        registry.solver_metadata("CBS").factory
    )
    cap = solvers.SolverRegistry.get_capability(name)
    assert cap.solver_id == name and cap.description == "Fixture metadata"
    assert name in {c.solver_id for c in solvers.SolverRegistry.list_capabilities()}


def test_unknown_solver_does_not_generate_a_request_schema(monkeypatch):
    def unexpected_schema():
        raise AssertionError("No descriptor is required for an absent solver")

    monkeypatch.setattr(JobSubmissionRequest, "model_json_schema", unexpected_schema)
    assert solvers.SolverRegistry.get_capability("missing-solver") is None
