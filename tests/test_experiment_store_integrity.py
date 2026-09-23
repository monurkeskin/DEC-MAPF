"""Resume and read-only recovery preserve the original experiment definition."""

import pytest

from mapf.application.experiment_store import SQLiteExperimentStore
from mapf.application.runs import RunRepository


def manifest():
    return {"experiment_id": "exp-fixture", "name": "recovery witness",
            "trials": [{"trial_id": "trial-one"}], "budget": {"wall_seconds": 20}}


def test_read_only_workspace_without_experiments_reports_missing_identity(tmp_path):
    RunRepository(tmp_path)
    store = SQLiteExperimentStore(RunRepository(tmp_path, read_only=True))
    assert store.manifests() == []
    for read in (store.manifest, store.progress, store.trial_ids):
        with pytest.raises(KeyError, match="unknown"):
            read("unknown")


def test_resume_refuses_changed_definition_and_preserves_charged_time(tmp_path):
    store = SQLiteExperimentStore(RunRepository(tmp_path))
    original = manifest()
    assert store.register(original, resume=False) == 0
    store.update(original["experiment_id"], "interrupted", 7.5)
    with pytest.raises(ValueError, match="already exists"):
        store.register(original, resume=False)
    with pytest.raises(ValueError, match="differs"):
        store.register(dict(original, budget={"wall_seconds": 200}), resume=True)
    assert store.register(original, resume=True) == 7.5
    assert store.manifest(original["experiment_id"]) == original
    assert store.progress(original["experiment_id"]) == ("interrupted", 7.5)
    assert store.trial_ids(original["experiment_id"]) == ["trial-one"]


def test_missing_experiment_cannot_be_updated_or_projected(tmp_path):
    store = SQLiteExperimentStore(RunRepository(tmp_path))
    for read in (store.manifest, store.progress, store.trial_ids):
        with pytest.raises(KeyError):
            read("unknown")
    with pytest.raises(KeyError):
        store.update("unknown", "completed", 0)
    assert store.manifests() == []
