"""Headless workflows exercise the real spawned solver and durable all-trial ledger."""

from copy import deepcopy

import pytest

from mapf.application.experiments import ExperimentService, compile_experiment
from mapf.application.runs import RunRepository


def spec():
    return {
        "name": "independent tiny acceptance",
        "scenarios": [{"scenario_id": "crossing-2a"}],
        "defaults": {"solver_id": "CBS", "setting": "SETTING_4", "timeout_sec": 10},
        "matrix": {"random_seed": [11, 12], "fov_size": [3, 5]},
        "exclude": [{"random_seed": 12, "fov_size": 5}],
        "budget": {"workers": 2, "wall_seconds": 30, "max_trials": 4, "disk_mb": 128},
        "sampling": {"population": "two deterministic fixture seeds", "independent_unit": "instance_hash"},
    }


def test_cartesian_exclusion_is_explicit_and_preview_does_not_execute():
    plan = compile_experiment(spec())
    assert len(plan["trials"]) == 3
    assert len(plan["excluded"]) == 1
    assert len({t["trial_id"] for t in plan["trials"]}) == 3
    assert all(t["plan"]["scenario"]["starts"] for t in plan["trials"])
    changed = spec()
    changed["matrix"]["fov_size"] = [3, 4]
    with pytest.raises(ValueError, match="odd"):
        compile_experiment(changed)


def test_headless_run_resume_and_exact_all_trial_denominator(tmp_path):
    plan = compile_experiment(spec())
    repository = RunRepository(tmp_path)
    service = ExperimentService(repository)
    result = service.execute(plan)
    assert result["counts"] == {"completed": 3}
    assert result["planned"] == 3
    assert result["successful"] == 3
    before = [j["job_id"] for j in repository.list_jobs()]
    repeated = service.execute(plan, resume=True)
    assert repeated["counts"] == {"completed": 3}
    assert [j["job_id"] for j in repository.list_jobs()] == before
    rows = service.rows(plan["experiment_id"])
    assert len(rows) == 3
    assert {row["instance_hash"] for row in rows} == {plan["trials"][0]["plan"]["scenario"]["instance_hash"]}


def test_manifest_tampering_and_source_change_rejected_before_admission(tmp_path):
    plan = compile_experiment(spec())
    changed = deepcopy(plan)
    changed["trials"][0]["plan"]["effective_config"]["random_seed"] = 444
    repository = RunRepository(tmp_path)
    with pytest.raises(ValueError, match="digest"):
        ExperimentService(repository).execute(changed)
    assert repository.list_jobs() == []


def test_owner_recovery_marks_abandoned_experiment_interrupted(tmp_path):
    service = ExperimentService(RunRepository(tmp_path))
    manifest = compile_experiment(spec())
    service.register(manifest)
    with service.repository.connect() as db:
        db.execute("UPDATE experiments SET state='running' WHERE id=?", (manifest['experiment_id'],))
    service.repository.recover()
    assert service.summary(manifest['experiment_id'])['state'] == 'interrupted'
    assert service.summary(manifest['experiment_id'])['counts'] == {'not_admitted': 3}
