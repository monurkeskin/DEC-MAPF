"""Resource pressure changes admission, never scientific outcomes or retry lineage."""

from copy import deepcopy

import pytest

from mapf.application.experiments import (
    ExperimentBudget,
    ExperimentService,
    compile_experiment,
)
from mapf.application.jobs import JobSupervisor
from mapf.application.resources import (
    MIB,
    ResourceAdmission,
    ResourcePolicy,
    ResourceSnapshot,
)
from mapf.application.runs import RunRepository


class FixedProbe:
    def __init__(self, snapshot: ResourceSnapshot) -> None:
        self.snapshot = snapshot

    def sample(self, processes: dict[str, int]) -> ResourceSnapshot:
        return self.snapshot


def job(name, solver):
    return {"job_id": name, "effective_config": {"solver_id": solver, "suboptimality": 1.0}}


def test_heavy_head_does_not_block_a_fitting_decentralized_job():
    waiting = [job("heavy", "CBS"), job("small", "Decentralized-HeatMap")]
    before = deepcopy(waiting)
    admission = ResourceAdmission(ResourcePolicy(), FixedProbe(ResourceSnapshot(6 * 1024 * MIB, 20)))
    assert [j["job_id"] for j in admission.choose(waiting, [], {}, 2)] == ["small"]
    assert admission.latest["blocked"] == {"heavy": "free_memory"}
    assert waiting == before


def test_reserved_growth_and_family_limits_are_accounted():
    policy = ResourcePolicy(optimal_reserve_mb=4096, centralized_slots=1, free_memory_mb=1024)
    probe = FixedProbe(ResourceSnapshot(4096 * MIB, 20, {"active": 3072 * MIB}))
    admission = ResourceAdmission(policy, probe)
    chosen = admission.choose([job("second", "CBS"), job("small", "Decentralized-HeatMap")],
                              [job("active", "CBS")], {"active": 123}, 2)
    assert [j["job_id"] for j in chosen] == ["small"]
    assert admission.latest["blocked"]["second"] == "centralized_slots"
    policy = policy.model_copy(update={"centralized_slots": 2})
    admission = ResourceAdmission(policy, probe)
    assert admission.choose([job("second", "CBS")], [job("active", "CBS")], {"active": 123}, 2) == []
    assert admission.latest["blocked"]["second"] == "free_memory"


@pytest.mark.parametrize("snapshot,reason", [
    (ResourceSnapshot(None, None, error="process access denied"), "resource_telemetry_unavailable"),
    (ResourceSnapshot(64 * 1024 * MIB, 99), "cpu_pressure"),
])
def test_missing_telemetry_or_cpu_pressure_never_admits(snapshot, reason):
    admission = ResourceAdmission(ResourcePolicy(), FixedProbe(snapshot))
    assert admission.choose([job("small", "Decentralized-HeatMap")], [], {}, 2) == []
    assert admission.latest["blocked"]["small"] == reason


def test_owned_reservation_ceiling_and_total_slots():
    admission = ResourceAdmission(ResourcePolicy(max_owned_memory_mb=300),
                                  FixedProbe(ResourceSnapshot(64 * 1024 * MIB, 0)))
    selected = admission.choose([job("a", "HeatMap"), job("b", "HeatMap")], [], {}, 2)
    assert len(selected) == 1
    assert admission.latest["blocked"]["b"] == "owned_memory_reservation"
    assert admission.choose([job("c", "HeatMap")], [], {}, 0) == []


def test_extra_workers_require_a_recorded_resource_policy():
    with pytest.raises(ValueError, match="explicit resource"):
        ExperimentBudget(workers=6)
    assert ExperimentBudget(workers=6, resources=ResourcePolicy()).workers == 6


def test_shared_supervisor_cannot_exceed_an_experiments_declared_workers():
    admission = ResourceAdmission(ResourcePolicy(decentralized_slots=6),
                                  FixedProbe(ResourceSnapshot(64 * 1024 * MIB, 0)))
    waiting = [dict(job(str(i), "HeatMap"), experiment_id="study", experiment_worker_limit=2) for i in range(4)]
    chosen = admission.choose(waiting, [], {}, 6)
    assert [j["job_id"] for j in chosen] == ["0", "1"]
    assert admission.latest["blocked"] == {"2": "experiment_worker_limit", "3": "experiment_worker_limit"}


def spec(policy=None):
    return {"name": "resource acceptance", "scenarios": [{"scenario_id": "crossing-2a"}],
            "defaults": {"solver_id": "CBS", "setting": "SETTING_4", "timeout_sec": 10},
            "matrix": {"random_seed": [1, 2]},
            "budget": {"workers": 2, "wall_seconds": 30, "resources": policy.model_dump() if policy else None}}


def test_real_jobs_retain_results_deadlines_and_resume_lineage(tmp_path):
    plain = compile_experiment(spec())
    reference = ExperimentService(RunRepository(tmp_path / "reference"))
    assert reference.execute(plain)["successful"] == 2
    policy = ResourcePolicy(optimal_reserve_mb=128, free_memory_mb=64)
    manifest = compile_experiment(spec(policy))
    repo = RunRepository(tmp_path / "resource")
    service = ExperimentService(repo)
    supervisor = JobSupervisor(repo, resource_policy=policy,
        resource_probe=FixedProbe(ResourceSnapshot(64 * 1024 * MIB, 0)))
    try:
        assert service.execute(manifest, supervisor=supervisor)["successful"] == 2
        before = [j["job_id"] for j in repo.list_jobs()]
        assert service.execute(manifest, resume=True, supervisor=supervisor)["successful"] == 2
        assert [j["job_id"] for j in repo.list_jobs()] == before
        for baseline, actual in zip(reference.rows(plain["experiment_id"]), service.rows(manifest["experiment_id"]), strict=True):
            assert actual["timeout_sec"] == baseline["timeout_sec"] == 10
            assert actual["sum_of_costs"] == baseline["sum_of_costs"]
            assert actual["makespan"] == baseline["makespan"]
            base_run = reference.repository.get_run(baseline["run_id"])
            run = repo.get_run(actual["run_id"])
            assert run["result"]["paths"] == base_run["result"]["paths"]
            assert run["metadata"]["resource_admission"]["policy"] == policy.model_dump()
    finally:
        supervisor.close()


def test_unavailable_resources_are_administrative_and_pending_jobs_remain_cancellable(tmp_path):
    policy = ResourcePolicy(idle_timeout_sec=0.1)
    repo = RunRepository(tmp_path)
    service = ExperimentService(repo)
    supervisor = JobSupervisor(repo, resource_policy=policy,
        resource_probe=FixedProbe(ResourceSnapshot(None, None, error="unavailable")))
    try:
        summary = service.execute(compile_experiment(spec(policy)), supervisor=supervisor)
        assert summary["state"] == "resource_blocked"
        assert summary["counts"] == {"interrupted": 2}
        assert summary["successful"] == 0
        assert all(j["started_at"] is None for j in repo.list_jobs())
        assert summary["workspace_resource_status"]["observation"]["error"] == "unavailable"
    finally:
        supervisor.close()


def test_gui_previews_actual_worker_limit_and_rejects_unconfigured_policy(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from mapf.gui.app import create_app

    monkeypatch.setenv("MAPF_WORKERS", "3")
    monkeypatch.delenv("MAPF_RESOURCE_POLICY", raising=False)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/v1/health").json()["worker_limit"] == 3
        preview = client.post("/api/v1/plans/preview", json={"jobs": [{"scenario_id": "crossing-2a"}]})
        assert preview.json()["max_concurrency"] == 3
        assert client.get("/api/v1/profiles/smoke-v1").json()["max_concurrency"] == 3
        manifest = compile_experiment(spec(ResourcePolicy()))
        response = client.post("/api/v1/experiments", json={"manifest": manifest})
        assert response.status_code == 422
        assert "resource policy" in response.json()["detail"]
        assert client.get("/api/v1/experiments").json() == []


@pytest.mark.parametrize("mismatch", ["resource policy", "worker budget"])
def test_python_preflight_rejects_owner_mismatch_without_registering_a_study(tmp_path, mismatch):
    repo = RunRepository(tmp_path)
    service = ExperimentService(repo)
    policy = ResourcePolicy() if mismatch == "resource policy" else None
    manifest = compile_experiment(spec(policy))
    supervisor = JobSupervisor(repo, max_workers=1 if mismatch == "worker budget" else 2)
    try:
        with pytest.raises(ValueError, match=mismatch):
            service.execute(manifest, supervisor=supervisor)
        assert service.manifests() == []
        assert repo.list_jobs() == []
    finally:
        supervisor.close()
