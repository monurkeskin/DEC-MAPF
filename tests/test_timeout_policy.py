"""Research process budgets have the same approved bound across entry points."""

import pytest
from fastapi.testclient import TestClient

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.experiments import compile_experiment
from mapf.application.plans import preview
from mapf.application.solvers import SolverRegistry
from mapf.gui.app import create_app


@pytest.mark.parametrize(
    "solver,seconds",
    [
        ("CBS", 600),
        ("EECBS-1.1", 600),
        ("Prioritized", 600),
        ("Decentralized-PathAware", 600),
        ("Decentralized-HeatMap", 600),
    ],
)
def test_declared_timeout_is_preserved_in_effective_plan_and_capabilities(
    solver, seconds
):
    request = JobSubmissionRequest(
        scenario_id="crossing-2a", solver_id=solver, timeout_sec=seconds
    )
    assert preview(request)["effective_config"]["timeout_sec"] == seconds
    cap = SolverRegistry.get_capability(solver)
    descriptor = next(p for p in cap.parameters if p.name == "timeout_sec")
    assert descriptor.max_value == seconds
    manifest = compile_experiment(
        {
            "name": "timeout boundary",
            "scenarios": [request.model_dump(mode="json")],
            "budget": {
                "workers": 1,
                "wall_seconds": seconds + 10,
                "max_trials": 1,
                "disk_mb": 64,
            },
        }
    )
    assert manifest["maximum_process_seconds"] == seconds


@pytest.mark.parametrize(
    "solver,seconds",
    [
        ("CBS", 600.1),
        ("EECBS-1.1", 601),
        ("Prioritized", 600.1),
        ("Decentralized-PathAware", 600.1),
    ],
)
def test_excessive_process_timeout_is_rejected_before_admission(
    solver, seconds, tmp_path
):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/jobs",
            json={
                "scenario_id": "crossing-2a",
                "solver_id": solver,
                "timeout_sec": seconds,
            },
        )
        assert response.status_code in {400, 422}, response.text
        assert client.get("/api/v1/jobs").json() == []
