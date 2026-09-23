"""Custom scenario admission keeps physical settings explicit across API and plans."""

import pytest
from fastapi.testclient import TestClient

from mapf.application.contracts import JobSubmissionRequest
from mapf.application.plans import preview
from mapf.application.scenarios import ScenarioService
from mapf.core.models import Point, SimulationSetting
from mapf.gui.app import create_app
from mapf.solvers.base import MAPFInstance


def scenario(**changes):
    values = {"grid_width": 3, "grid_height": 2, "starts": {"a": Point(0, 0)},
              "goals": {"a": Point(2, 0)}, "obstacles": set()}
    return MAPFInstance(**(values | changes))


@pytest.mark.parametrize(("changes", "message"), [
    ({"grid_width": 0}, "Invalid grid"),
    ({"starts": {}, "goals": {}}, "between 1 and 100"),
    ({"starts": {"": Point(0, 0)}, "goals": {"": Point(2, 0)}}, "1 to 64"),
    ({"obstacles": {Point(3, 0)}}, "Obstacle out of bounds"),
    ({"starts": {"a": Point(-1, 0)}}, "out of bounds"),
    ({"obstacles": {Point(2, 0)}}, "on obstacle"),
], ids=["dimension", "empty", "agent-id", "obstacle", "start", "blocked-goal"])
def test_semantic_validation_names_invalid_geometry(changes, message):
    errors = ScenarioService.validate_instance(scenario(**changes))
    assert any(message in error for error in errors)


def test_saved_scenario_can_be_listed_loaded_and_planned_under_explicit_setting(tmp_path):
    snapshot = ScenarioService.snapshot_instance(scenario(), SimulationSetting.SETTING_4)
    request = {key: snapshot[key] for key in ("grid_width", "grid_height", "starts", "goals", "obstacles", "setting")}
    with TestClient(create_app(tmp_path)) as client:
        assert client.post("/api/v1/scenarios/validate", json=request).json()["is_valid"]
        saved = client.post("/api/v1/scenarios", json=request)
        assert saved.status_code == 201
        sid = saved.json()["scenario_id"]
        assert client.get(f"/api/v1/scenarios/{sid}").json()["starts"] == request["starts"]
        listing = client.get("/api/v1/scenarios").json()
        summary = next(row for row in listing if row["scenario_id"] == sid)
        assert summary["agent_count"] == 1 and summary["density"] == 0
        repository, _ = client.app.state.workspace_services()
        plan = preview(JobSubmissionRequest(scenario_id=sid, solver_id="CBS", setting="SETTING_1"), repository)
        assert plan["scenario"]["setting"] == "SETTING_1"
        assert client.get("/api/v1/scenarios/scenario-00000000000000000000000000000000").status_code == 404


def test_setting_change_cannot_admit_shared_goals_for_staying_agents(tmp_path):
    instance = scenario(starts={"a": Point(0, 0), "b": Point(0, 1)},
                        goals={"a": Point(2, 0), "b": Point(2, 0)})
    from mapf.application.runs import RunRepository
    repository = RunRepository(tmp_path)
    sid = repository.save_scenario(ScenarioService.snapshot_instance(instance, SimulationSetting.SETTING_4))
    staying = next(setting for setting in SimulationSetting if not setting.disappear_at_target)
    with pytest.raises(ValueError, match="Shared goals"):
        preview(JobSubmissionRequest(scenario_id=sid, setting=staying.name), repository)


def test_unknown_scenario_is_not_substituted_with_a_builtin():
    with pytest.raises(KeyError, match="missing"):
        preview(JobSubmissionRequest(scenario_id="missing"))


def test_solver_process_limit_cannot_be_bypassed_with_unvalidated_model_copy():
    request = JobSubmissionRequest(scenario_id="crossing-2a", solver_id="CBS")
    with pytest.raises(ValueError, match="timeout must not exceed"):
        preview(request.model_copy(update={"timeout_sec": 601}))
