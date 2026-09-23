"""Exercise the researcher-facing teaching capsule, including failed trials."""
import json
from pathlib import Path

import pytest

from mapf.application.capsules import run_capsule
from mapf.application.experiments import ExperimentService


def capsule_spec():
    spec = json.loads(Path('examples/capsules/settings/study.json').read_text())
    spec['scenarios'] = [{'scenario_id': 'grid-8x8-4a'}]
    spec['matrix'] = {'solver_id': ['CBS'], 'setting': ['SETTING_4'], 'max_steps': [1, 40]}
    return spec


def test_capsule_preserves_failed_trials_and_exports_checked_replays(tmp_path, capsys):
    output = tmp_path / 'capsule'
    receipt = run_capsule(capsule_spec(), output)
    capsys.readouterr()
    rows = json.loads((output / 'all-trials.json').read_text())
    assert len(rows) == 2
    assert sum(row['success'] for row in rows) == 1
    assert len(receipt['bundle_checks']) == 2
    assert all((output / row['run_id'] / 'replay.html').is_file() for row in rows)
    assert (output / 'experiment-card.json').is_file()
    assert json.loads((output / 'receipt.json').read_text()) == receipt
    for row in rows:
        bundle = json.loads((output / row['run_id'] / 'bundle.json').read_text())
        assert bundle['format'] == 'decmapf-run'
        assert len(bundle['sha256']) == 64
        assert bundle['payload']['result']['success'] == row['success']


@pytest.mark.parametrize('budget,value', [('workers', 2), ('wall_seconds', 121)])
def test_capsule_budget_rejected_before_creating_output(tmp_path, budget, value):
    spec = capsule_spec()
    spec['budget'][budget] = value
    output = tmp_path / 'capsule'
    with pytest.raises(ValueError, match='Capsules are limited'):
        run_capsule(spec, output)
    assert not output.exists()


def test_capsule_never_overwrites_existing_study(tmp_path):
    sentinel = tmp_path / 'original.txt'
    sentinel.write_text('previous study')
    with pytest.raises(FileExistsError):
        run_capsule(capsule_spec(), tmp_path)
    assert sentinel.read_text() == 'previous study'


def test_unstarted_trials_stay_visible_without_exporting_nonexistent_artifacts(tmp_path, monkeypatch):
    def stop_before_admission(service, manifest):
        service.register(manifest)
        service.store.update(manifest['experiment_id'], 'interrupted', 0)
        return service.summary(manifest['experiment_id'])

    monkeypatch.setattr(ExperimentService, 'execute', stop_before_admission)
    output = tmp_path / 'interrupted'
    receipt = run_capsule(capsule_spec(), output)
    rows = json.loads((output / 'all-trials.json').read_text())
    assert len(rows) == 2 and all(row['state'] == 'not_admitted' for row in rows)
    assert receipt['bundle_checks'] == [] and receipt['story_run_id'] is None
    assert not list(output.glob('*/replay.html'))


def test_negotiation_capsule_exports_first_recorded_agreement(tmp_path):
    spec = json.loads(Path('examples/capsules/negotiation/study.json').read_text())
    spec['scenarios'] = [{'scenario_id': 'crossing-2a'}]
    output = tmp_path / 'negotiation'
    receipt = run_capsule(spec, output)
    assert receipt['story_run_id'] is not None
    story = json.loads((output / 'negotiation-story.json').read_text())
    assert story and (output / 'negotiation-story.html').is_file()
    rows = json.loads((output / 'all-trials.json').read_text())
    assert receipt['story_run_id'] == rows[0]['run_id']
