"""Public exports must not expose private history, raw data or filesystem links."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location('public_export', Path(__file__).parents[1] / 'scripts/public_export.py')
assert _spec and _spec.loader
export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export)


def repo(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    subprocess.run(['git', 'init', '-q', str(source)], check=True)
    for name, data in {'pyproject.toml': 'name = "example"', 'src/mapf/cli.py': '# public entry',
                       'benchmarks/results/raw.csv': 'private observation', 'README.md': '# Example'}.items():
        p = source / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)
    commit(source)
    return source


def commit(source):
    subprocess.run(['git', 'add', '--all'], cwd=source, check=True)
    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-qm', 'fixture'], cwd=source, check=True)


def test_export_reads_committed_files_without_raw_data_history_or_dirty_changes(tmp_path):
    source = repo(tmp_path)
    (source / 'README.md').write_text('uncommitted private note')
    (source / 'untracked.txt').write_text('untracked')
    target = tmp_path / 'export'
    manifest = export.export_snapshot(source, target)
    assert (target / 'README.md').read_text() == '# Example'
    assert not (target / '.git').exists()
    assert not (target / 'benchmarks/results/raw.csv').exists()
    assert not (target / 'untracked.txt').exists()
    assert manifest['audit']['files'] == 3
    published = json.loads((target / 'PUBLICATION-MANIFEST.json').read_text())
    assert 'source_commit' not in published
    assert len(published['content_sha256']) == 64


def test_export_refuses_existing_output(tmp_path):
    source = repo(tmp_path)
    with pytest.raises(ValueError, match='must not exist'):
        export.export_snapshot(source, source)


def test_export_refuses_a_tracked_symlink_before_writing(tmp_path):
    source = repo(tmp_path)
    (source / 'docs').mkdir()
    (source / 'docs/leak.md').symlink_to(source / 'benchmarks/results/raw.csv')
    commit(source)
    target = tmp_path / 'export'
    with pytest.raises(ValueError, match='regular tracked files'):
        export.export_snapshot(source, target)
    assert not target.exists()


@pytest.mark.parametrize('payload', [b'co-' + b'author preview', b'/Users/' + b'somebody/notes',
                                     b'-----BEGIN ' + b'PRIVATE KEY-----'])
def test_export_refuses_confidential_material_without_echoing_it(payload):
    with pytest.raises(ValueError, match='README.md') as error:
        export.check_payloads({'README.md': payload})
    assert payload.decode() not in str(error.value)


@pytest.mark.parametrize('name', ['../README.md', '/README.md', 'docs/.env', 'tests/secret.key',
                                 'frontend/node_modules/x.js', 'benchmarks/data/table.csv'])
def test_export_excludes_unapproved_paths(name):
    assert not export.exportable(name)


@pytest.mark.parametrize('payload', [
    b'## Version ' + b'99: obsolete development heading',
    b'## Engineering ' + b'revision 99: obsolete note',
    b'Algorithm: modern-python-' + b'v99-example',
    b'{"git_commit": "' + b'a' * 40 + b'"}',
])
def test_initial_publication_rejects_internal_chronology_and_private_commit_literals(payload):
    with pytest.raises(ValueError, match='docs/method.md'):
        export.check_payloads({'docs/method.md': payload})


@pytest.mark.parametrize('name', ['docs/releases/' + 'v9.9.9.md',
                                 'benchmarks/' + 'historical-artifacts.json'])
def test_initial_publication_excludes_internal_history_files(name):
    assert not export.exportable(name)


def test_current_alpha_and_upstream_identity_remain_valid_documentation():
    payload = (b'Alpha 0.1.0a1; /api/v1; taop-v2; Python 3.12; '
               b'https://github.com/Jiaoyang-Li/EECBS/tree/' + b'a' * 40)
    assert export.check_payloads({'README.md': payload})['status'] == 'passed'
