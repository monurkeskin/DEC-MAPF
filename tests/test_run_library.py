"""Independent listing witnesses: no solver outcomes are fabricated as research data."""
import json

import pytest
from fastapi.testclient import TestClient

from mapf.application.runs import RunRepository
from mapf.gui.app import create_app


def add_summary(repo, index, timestamp=100):
    summary = {"run_id": f"run-{index:032x}", "instance_hash": "listing-fixture", "solver_name": "fixture",
        "setting": "SETTING_1", "agent_count": 0, "grid_width": 4, "grid_height": 4, "success": False,
        "is_valid": False, "validation_status": "not_checked", "makespan": 0, "sum_of_costs": 0,
        "runtime_ms": 0, "frame_count": 0, "timestamp": timestamp}
    with repo.connect() as db:
        db.execute("INSERT INTO runs(id,sha256,summary,created) VALUES(?,?,?,?)",
                   (summary["run_id"], "listing-only", json.dumps(summary), timestamp))
    return summary["run_id"]


def test_pagination_visits_every_original_row_once_across_ties_and_insertions(tmp_path):
    repo = RunRepository(tmp_path)
    original = [add_summary(repo, index) for index in range(121)]
    with TestClient(create_app(tmp_path)) as client:
        first = client.get("/api/v1/runs/page?limit=100")
        assert first.status_code == 200, first.text
        page = first.json()
        seen = [r["run_id"] for r in page["items"]]
        add_summary(repo, 500, timestamp=101)
        # Deleting an already returned record must not shift the next page.
        with repo.connect() as db:
            db.execute("DELETE FROM runs WHERE id=?", (seen[0],))
        following = client.get("/api/v1/runs/page", params={"limit": 100, "cursor": page["next_cursor"]}).json()
        seen += [r["run_id"] for r in following["items"]]
        assert seen == sorted(original, reverse=True)
        assert following["next_cursor"] is None
        assert client.get("/api/v1/runs?limit=1").json()[0]["run_id"] == f"run-{500:032x}"


def test_filters_apply_before_pagination_and_cursor_is_bound_to_filters(tmp_path):
    repo = RunRepository(tmp_path)
    for index in range(3):
        add_summary(repo, index)
    with TestClient(create_app(tmp_path)) as client:
        page = client.get("/api/v1/runs/page", params={"limit": 1, "solver_name": "fixture"}).json()
        assert page["total"] == 3
        assert client.get("/api/v1/runs/page", params={"solver_name": "missing"}).json()["items"] == []
        assert client.get("/api/v1/runs/page", params={"experiment_id": "missing"}).json()["total"] == 0
        changed = client.get("/api/v1/runs/page", params={"solver_name": "different", "cursor": page["next_cursor"]})
        assert changed.status_code == 422
        assert "filter" in changed.json()["detail"].lower()


@pytest.mark.parametrize("cursor", ["not!base64", "e30=", "A" * 2000])
def test_bad_cursor_is_a_client_error(tmp_path, cursor):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/v1/runs/page", params={"cursor": cursor}).status_code in (400, 422)
