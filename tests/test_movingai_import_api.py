"""Uploaded map files must fail at the HTTP boundary, before persistence."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from mapf.gui.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path), raise_server_exceptions=False) as value:
        yield value


@pytest.fixture
def upload():
    return {
        "map_text": "type octile\nheight 3\nwidth 3\nmap\n...\n.@.\n...\n",
        "scenario_text": "version 1\n0 tiny.map 3 3 0 0 2 2 4\n",
        "agent_count": 1,
        "setting": "SETTING_4",
    }


@pytest.mark.parametrize("dimension", ["width", "height"])
def test_missing_map_dimension_is_a_client_error(client, upload, dimension):
    upload["map_text"] = upload["map_text"].replace(f"{dimension} 3", dimension)
    response = client.post("/api/v1/scenarios/import-movingai", json=upload)
    assert response.status_code == 422, response.text
    assert response.json()["kind"] == "invalid_input_or_artifact"
    assert all("source" not in row for row in client.get("/api/v1/scenarios").json())


@pytest.mark.parametrize("distance", ["nan", "inf", "-1", "not-a-number"])
def test_invalid_scenario_distance_is_rejected(client, upload, distance):
    upload["scenario_text"] = f"version 1\n0 tiny.map 3 3 0 0 2 2 {distance}\n"
    response = client.post("/api/v1/scenarios/import-movingai", json=upload)
    assert response.status_code == 422, response.text


def test_invalid_unselected_row_is_not_silently_accepted(client, upload):
    upload["scenario_text"] += "1 tiny.map 3 3 99 0 1 2 4\n"
    response = client.post("/api/v1/scenarios/import-movingai", json=upload)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "replacement",
    [
        {"map_text": "not a map"},
        {"map_text": "type octile\nheight 1\nwidth 65\nmap\n" + "." * 65},
        {"map_text": "type octile\nheight 1\nwidth 1\nmap\nX"},
        {"scenario_text": "version 2"},
        {"scenario_text": "version 1\n0 tiny.map 3 3 0 0 2 2"},
        {"scenario_text": "version 1\n0 tiny.map 4 3 0 0 2 2 4"},
        {"scenario_text": "version 1"},
        {"agent_count": 2},
        {"scenario_text": "version 1\n0 tiny.map 3 3 1 1 2 2 2"},
        {
            "scenario_text": "version 1\n0 tiny.map 3 3 0 0 2 2 4\n1 other.map 3 3 2 0 0 2 4"
        },
    ],
    ids=[
        "header",
        "workspace-size",
        "terrain",
        "version",
        "columns",
        "map-size",
        "no-rows",
        "selection",
        "blocked-start",
        "mixed-maps",
    ],
)
def test_rejected_imports_do_not_add_partial_scenarios(client, upload, replacement):
    before = client.get("/api/v1/scenarios").json()
    response = client.post(
        "/api/v1/scenarios/import-movingai", json={**upload, **replacement}
    )
    assert response.status_code == 422, response.text
    assert client.get("/api/v1/scenarios").json() == before


def test_import_allows_standard_comments_without_changing_row_selection(client, upload):
    upload["scenario_text"] = (
        "version 1\n# one map, one pair\n\n0 tiny.map 3 3 0 0 2 2 4\n"
    )
    response = client.post("/api/v1/scenarios/import-movingai", json=upload)
    assert response.status_code == 201, response.text
    assert response.json()["starts"] == {"agent_0": [0, 0]}


def test_decimal_version_header_keeps_raw_source_provenance(client, upload):
    upload["scenario_text"] = upload["scenario_text"].replace(
        "version 1", "version 1.0"
    )
    response = client.post("/api/v1/scenarios/import-movingai", json=upload)
    assert response.status_code == 201, response.text
    assert (
        response.json()["source"]["scenario_sha256"]
        == hashlib.sha256(upload["scenario_text"].encode()).hexdigest()
    )


def test_import_retains_order_raw_source_hashes_and_immutable_snapshot(client, upload):
    upload["scenario_text"] += "1 tiny.map 3 3 2 0 0 2 4\n"
    upload["agent_count"] = 2
    response = client.post("/api/v1/scenarios/import-movingai", json=upload)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["starts"] == {"agent_0": [0, 0], "agent_1": [2, 0]}
    assert saved["goals"] == {"agent_0": [2, 2], "agent_1": [0, 2]}
    assert saved["obstacles"] == [[1, 1]]
    assert saved["source"] == {
        "format": "MovingAI",
        "map_sha256": hashlib.sha256(upload["map_text"].encode()).hexdigest(),
        "scenario_sha256": hashlib.sha256(upload["scenario_text"].encode()).hexdigest(),
        "selection": "first 2 rows; no random subsample",
    }
    loaded = client.get(f"/api/v1/scenarios/{saved['scenario_id']}").json()
    assert loaded["source"] == saved["source"]
    assert loaded["instance_hash"] == saved["instance_hash"]
