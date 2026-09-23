"""The same named preset means the same experiment through every entry point."""
import pytest
from fastapi.testclient import TestClient

from mapf.application.experiments import compile_experiment
from mapf.application.plans import preview
from mapf.application.presets import preset_request
from mapf.gui.app import create_app


def test_named_starter_has_identical_http_python_and_batch_definition(tmp_path):
    request = preset_request("interactive-v1", scenario_id="crossing-2a")
    expected = preview(request)
    with TestClient(create_app(tmp_path)) as client:
        preset = client.get("/api/v1/presets/interactive-v1").json()
        assert preset["inputs"]["timeout_sec"] == 10
        assert preset["inputs"]["verification_pass_limit"] == 3
        actual = client.post("/api/v1/plans/preview", json={"jobs": [{**preset["inputs"], "scenario_id": "crossing-2a"}]})
        assert actual.status_code == 200, actual.text
        assert actual.json()["plans"][0]["definition_digest"] == expected["definition_digest"]
    experiment = compile_experiment({"name": "named starter witness", "preset_id": "interactive-v1",
        "scenarios": [{"scenario_id": "crossing-2a"}]})
    assert experiment["trials"][0]["plan"]["definition_digest"] == expected["definition_digest"]


def test_explicit_values_override_preset_and_instances_do_not_share_mutable_values():
    first = preset_request("interactive-v1", timeout_sec=600)
    assert first.timeout_sec == 600
    first.starts["A"] = {"x": 1, "y": 0}
    assert preset_request("interactive-v1").starts == {}
    with pytest.raises(ValueError, match="Unknown preset"):
        preset_request("interactiv-v1")
