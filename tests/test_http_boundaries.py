"""Exercise real HTTP admission, transport errors and compatibility exports."""

import json

import polars as pl
import pytest
from fastapi.testclient import TestClient

from mapf.gui import _legacy_archives, _legacy_benchmarks
from mapf.gui.app import create_app
from mapf.gui.batch_manager import BenchmarkTaskManager, BenchmarkTaskProgress


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "workspace")) as client:
        yield client


@pytest.mark.parametrize(("error", "status", "kind"), [
    (ValueError("bad manifest"), 422, "invalid_input_or_artifact"),
    (KeyError("missing"), 404, None),
    (OverflowError("queue full"), 429, "local_capacity"),
    (OSError("disk full"), 507, "storage_failure"),
], ids=["input", "missing", "capacity", "storage"])
def test_http_errors_keep_structured_diagnostics(client, error, status, kind):
    @client.app.get("/test-failure")
    async def failure():
        raise error

    response = client.get("/test-failure")
    assert response.status_code == status
    assert str(error) in response.json()["detail"]
    assert response.json().get("kind") == kind


def test_large_untrusted_body_is_rejected_before_a_workspace_is_created(tmp_path):
    with TestClient(create_app(tmp_path / "workspace")) as client:
        result = client.post("/api/v1/jobs", content=b"x" * (16 * 1024 * 1024 + 1))
    assert result.status_code == 413
    assert not (tmp_path / "workspace").exists()


@pytest.mark.parametrize("origin", ["https://example.invalid", "null", "file://"])
def test_nonlocal_browser_origins_cannot_mutate_the_workspace(client, origin):
    response = client.post("/api/v1/jobs", json={}, headers={"origin": origin})
    assert response.status_code == 403


@pytest.fixture
def task(monkeypatch):
    manager = BenchmarkTaskManager()
    task = BenchmarkTaskProgress("task-fixture", "quick_test", 1)
    manager._tasks[task.task_id] = task
    monkeypatch.setattr(_legacy_benchmarks, "benchmark_manager", manager)
    return task


def test_retired_batch_routes_still_inspect_and_cancel_existing_tasks(client, task):
    listed = client.get("/api/benchmark/tasks").json()
    assert [row["task_id"] for row in listed] == [task.task_id]
    status = client.get(f"/api/benchmark/status/{task.task_id}").json()
    assert status["results_count"] == 0 and status["status"] == "RUNNING"
    assert client.post(f"/api/benchmark/cancel/{task.task_id}").status_code == 200
    response = client.get(f"/api/benchmark/stream/{task.task_id}")
    assert response.status_code == 200 and "event: task_cancelled" in response.text
    assert task.status == "CANCELLED"


def test_cancel_request_does_not_relabel_a_completed_legacy_task(client, task):
    task.status = "COMPLETED"
    response = client.post(f"/api/benchmark/cancel/{task.task_id}")
    assert response.status_code == 409
    assert task.status == "COMPLETED" and not task.cancelled


@pytest.mark.parametrize("route", ["status", "stream", "cancel"])
def test_missing_legacy_tasks_report_404(client, route):
    method = client.post if route == "cancel" else client.get
    assert method(f"/api/benchmark/{route}/absent").status_code == 404


@pytest.mark.parametrize(("headers", "query", "ids"), [
    ({"Last-Event-ID": "1"}, "?cursor=0", [2]),
    ({"Last-Event-ID": "invalid"}, "?cursor=1", [1, 2]),
    ({}, "?cursor=1", [2]),
], ids=["header", "invalid-header", "query"])
def test_legacy_stream_preserves_cursor_precedence(client, task, headers, query, ids):
    task.append_event("run_completed", {})
    task.append_event("suite_finished", {})
    task.status = "COMPLETED"
    response = client.get(f"/api/benchmark/stream/{task.task_id}{query}", headers=headers)
    records = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [record["id"] for record in records] == ids


@pytest.fixture
def archives(tmp_path, monkeypatch):
    monkeypatch.setattr(_legacy_archives, "__file__", str(tmp_path / "src/mapf/gui/archive.py"))
    folder = tmp_path / "benchmarks/results"
    folder.mkdir(parents=True)
    return folder


def test_legacy_archive_table_reports_observed_sample_mean(client, archives):
    pl.DataFrame({"map_name": ["test_map"] * 2, "setting_name": ["SETTING_1"] * 2,
                  "fov": [5, 5], "success": [True, False]}).write_parquet(archives / "appendix_32x32_results.parquet")
    response = client.get("/api/results/appendix_32x32").json()
    assert response["total_rows"] == 2 and len(response["records"]) == 2
    latex = client.get("/api/export/latex/appendix_32x32").json()["latex"]
    assert r"test\_map & SETTING\_1 & 5 & 50.0\%" in latex
    assert r"\begin{tabular}{lllr}" in latex


def test_legacy_commitment_table_keeps_units_and_aggregation(client, archives):
    pl.DataFrame({"setting_name": ["SETTING_4"] * 2, "commitment": ["ZERO"] * 2,
                  "fov": [5, 5], "success": [True, False], "norm_path_diff": [10., 20.],
                  "negotiations": [4, 6]}).write_parquet(archives / "commitment_types_results.parquet")
    latex = client.get("/api/export/latex/commitment_types").json()["latex"]
    assert r"SETTING\_4 & ZERO & 5 & 50.0\% & 15.00\% & 5.0" in latex


@pytest.mark.parametrize("suite", ["appendix_32x32", "commitment_types"])
def test_missing_archive_is_unavailable_not_zero_performance(client, archives, suite):
    assert client.get(f"/api/results/{suite}").status_code == 404
    assert client.get(f"/api/export/latex/{suite}").status_code == 404
    assert client.get("/api/results/unknown").status_code == 404
    assert "No LaTeX template" in client.get("/api/export/latex/unknown").json()["latex"]
