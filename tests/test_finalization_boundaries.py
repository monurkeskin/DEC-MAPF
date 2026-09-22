"""Independent failure boundaries for the final local research workflow."""
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest

from mapf.agents.greedy import GreedyAgent
from mapf.application.article_suite import article_spec
from mapf.application.contracts import JobSubmissionRequest
from mapf.application.experiments import (
    ExperimentCoordinator,
    ExperimentService,
    compile_experiment,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.legacy import quarantine_table
from mapf.application.runs import TERMINAL, RunRepository
from mapf.core.geometry import goal_distances, grid_index
from mapf.core.models import Point
from mapf.core.movingai import format_movingai_map, format_movingai_scen
from mapf.negotiation.ledger import restore_agent, snapshot_agent
from mapf.telemetry.schema import EVENT_ADAPTER
from tests.test_workspace_services import uncooperative_worker


def test_static_topology_and_goal_cache_invalidate_without_mutable_aliases():
    opened = grid_index(3, 2, frozenset())
    blocked = grid_index(3, 2, frozenset({(1, 0), (1, 1)}))
    assert opened.components[(0, 0)] == opened.components[(2, 0)]
    assert blocked.components[(0, 0)] != blocked.components[(2, 0)]
    assert goal_distances(3, 2, frozenset(), (2, 0))[(0, 0)] == 2
    assert (0, 0) not in goal_distances(3, 2, frozenset({(1, 0), (1, 1)}), (2, 0))
    assert goal_distances(3, 2, frozenset(), (2, 1))[(0, 0)] == 3
    with pytest.raises(TypeError):
        opened.components[(0, 0)] = 90
    assert grid_index.cache_info().maxsize == 32
    assert goal_distances.cache_info().maxsize == 256


def test_snapshot_copies_owned_plugin_state_but_preserves_pydantic_deepcopy():
    a = GreedyAgent("a", Point(0, 0), Point(4, 0), 5)
    a.plugin_state = {"seen": [a.current_pos], "nested": {"calls": 0}}
    before = snapshot_agent(a)
    a.plugin_state["nested"]["calls"] = 7
    a.plugin_state["seen"].append(Point(1, 0))
    restore_agent(a, before)
    assert a.plugin_state == {"seen": [Point(0, 0)], "nested": {"calls": 0}}
    copied = a.current_pos.model_copy(deep=True, update={"x": 9})
    assert copied.x == 9 and a.current_pos.x == 0


@pytest.mark.parametrize("extension", ["csv", "parquet", "xlsx"])
def test_legacy_import_preserves_source_nulls_and_refuses_inferred_qualification(tmp_path, extension):
    frame = pd.DataFrame({"seed": [42, 51], "success": [True, False], "cost": [7, None]})
    source = tmp_path / f"historical.{extension}"
    getattr(frame, f"to_{'excel' if extension == 'xlsx' else extension}")(source, index=False)
    before = source.read_bytes()
    receipt = quarantine_table(source, tmp_path / "archive", "historical-empirical")
    assert source.read_bytes() == before
    assert receipt["eligible_for_current_comparison"] is False
    folder = tmp_path / "archive" / receipt["source_sha256"]
    assert (folder / source.name).read_bytes() == before
    assert '"cost":null' in (folder / "sheet-0.json").read_text().replace(' ', '')
    assert quarantine_table(source, tmp_path / "archive", "historical-empirical") == receipt
    with pytest.raises(ValueError, match="classified differently"):
        quarantine_table(source, tmp_path / "archive", "synthetic-demo")


def test_article_selection_freezes_rejected_rows_nested_prefixes_and_source_hashes(tmp_path):
    map_file = tmp_path / "fixture.map"
    map_file.write_text(format_movingai_map(8, 8, set()))
    pairs = [(Point(0, 0), Point(1, 0)), (Point(0, 1), Point(7, 1)),
             (Point(0, 2), Point(7, 2)), (Point(0, 1), Point(7, 3))]
    scene = tmp_path / "fixture-random-1.scen"
    scene.write_text(format_movingai_scen(pairs, map_file.name, 8, 8))
    spec = article_spec(map_file, [scene], agents=[1, 2], fovs=[5], workers=1,
                        wall_seconds=10, timeout_sec=2, split="development")
    source = spec["sampling"]["sources"][0]
    assert source["selected_prefixes"]["2"] == [{"row": 2, "distance": 7}, {"row": 3, "distance": 7}]
    assert [r["row"] for r in source["rejected_rows"]] == [1, 4]
    assert len({s["sampling_unit"] for s in spec["scenarios"]}) == 1
    assert len(compile_experiment(spec)["trials"]) == 16
    with pytest.raises(ValueError, match="different map"):
        scene.write_text(scene.read_text().replace('fixture.map', 'wrong.map'))
        article_spec(map_file, [scene], agents=[1], fovs=[5], workers=1,
                     wall_seconds=10, timeout_sec=2, split="held-out")


def test_concurrent_admission_same_idempotency_key_has_one_attempt(tmp_path):
    repo = RunRepository(tmp_path)
    supervisor = JobSupervisor(repo, max_workers=1, max_pending=2, worker=uncooperative_worker)
    try:
        request = JobSubmissionRequest(scenario_id="crossing-2a", solver_id="CBS", timeout_sec=20)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: supervisor.submit(request, "same-key"), range(8)))
        assert len({r["job_id"] for r in results}) == 1
        assert len(repo.list_jobs()) == 1
    finally:
        supervisor.close()
    assert repo.list_jobs()[0]["state"] == "interrupted"


def test_stopping_shared_experiment_preserves_other_jobs_and_retry_parent(tmp_path):
    repo = RunRepository(tmp_path)
    supervisor = JobSupervisor(repo, max_workers=2, worker=uncooperative_worker)
    service = ExperimentService(repo)
    driver = ExperimentCoordinator(service, supervisor)
    try:
        unrelated = supervisor.submit(JobSubmissionRequest(scenario_id="crossing-2a", solver_id="CBS", timeout_sec=30))
        manifest = compile_experiment({"name": "stop ownership", "scenarios": [{"scenario_id": "crossing-2a"}],
          "defaults": {"solver_id": "CBS", "timeout_sec": 30},
          "budget": {"workers": 1, "wall_seconds": 60, "max_trials": 1, "disk_mb": 128}})
        driver.start(manifest)
        deadline = time.monotonic() + 10
        while not service.attempts(manifest["experiment_id"]):
            assert time.monotonic() < deadline
            time.sleep(.02)
        driver.close()
        assert driver.error is None
        assert repo.get_job(unrelated["job_id"])["state"] not in TERMINAL
        first = service.rows(manifest["experiment_id"])[0]
        assert first["state"] == "interrupted"
        retry = supervisor.retry(first["job_id"])
        assert retry["parent_job_id"] == first["job_id"]
        assert retry["attempt_id"] != repo.get_job(first["job_id"])["attempt_id"]
        assert retry["effective_config"] == repo.get_job(first["job_id"])["effective_config"]
    finally:
        driver.close()
        supervisor.close()


def test_current_telemetry_union_rejects_unknown_major_and_missing_or_wrong_field():
    record = {"event_type": "MOVE", "tick": 1, "schema_version": "telemetry-2", "sequence": 1,
              "phase": "post_move", "agent_id": "a", "x": 0, "y": 1, "is_waiting": False, "remaining_dist": 1}
    assert EVENT_ADAPTER.validate_python(record).event_type == "MOVE"
    for changed in [dict(record, schema_version="telemetry-99"), dict(record, x="0"),
                    {k: v for k, v in record.items() if k != "agent_id"}]:
        with pytest.raises(ValueError):
            EVENT_ADAPTER.validate_python(changed)


def cpu_heavy_worker(job, output, connection):
    # Deliberately spends CPU in the owned child, independent of a solver's speed.
    deadline = time.monotonic() + 20
    value = 1
    while time.monotonic() < deadline:
        value = (value * 1103515245 + 12345) % 2147483647


def test_http_remains_responsive_with_two_busy_children(tmp_path):
    from fastapi.testclient import TestClient

    from mapf.gui.app import create_app
    app = create_app(tmp_path)
    with TestClient(app) as client:
        repo, supervisor = app.state.workspace_services()
        supervisor.worker = cpu_heavy_worker
        jobs = [supervisor.submit(JobSubmissionRequest(scenario_id="crossing-2a", timeout_sec=30)) for _ in range(2)]
        deadline = time.monotonic() + 10
        while any(repo.get_job(j["job_id"])["state"] != "running" for j in jobs):
            assert time.monotonic() < deadline
            time.sleep(.02)
        latencies = []
        for _ in range(10):
            start = time.monotonic()
            response = client.get('/api/v1/health')
            assert response.status_code == 200, response.text
            latencies.append(time.monotonic() - start)
        assert max(latencies) < 1, latencies
        for job in jobs:
            assert supervisor.cancel_job(job['job_id'])
        (tmp_path / 'responsiveness.json').write_text(__import__('json').dumps({'seconds': latencies, 'worker_count': 2}))


def test_quota_scan_tolerates_file_unlinked_between_listing_and_stat(tmp_path, monkeypatch):
    # SQLite WAL/SHM or an atomically published staging file may disappear while
    # health/quota sampling traverses an otherwise healthy active workspace.
    repository = RunRepository(tmp_path)
    target = tmp_path / 'transient-wal'
    target.write_bytes(b'nonempty')
    original_stat = Path.stat
    calls = 0
    def racing_stat(self, *args, **kwargs):
        nonlocal calls
        if self == target:
            calls += 1
            if calls == 2:
                self.unlink()
        return original_stat(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', racing_stat)
    assert repository.usage_bytes() >= 0
    assert not target.exists()
