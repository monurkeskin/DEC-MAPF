"""Distribution notices must track actual locked components, not a hand-written list."""
import json
import runpy
import shutil
from pathlib import Path

import pytest


@pytest.mark.parametrize('fault', [None, 'lock', 'omission', 'text', 'docs_text', 'duplicate'])
def test_notice_inventory_rejects_stale_or_missing_coverage(tmp_path, fault):
    source = Path(__file__).resolve().parents[1]
    (tmp_path / 'frontend').mkdir()
    shutil.copyfile(source / 'frontend/package-lock.json', tmp_path / 'frontend/package-lock.json')
    shutil.copytree(source / 'docs/licenses', tmp_path / 'docs/licenses')
    if fault == 'lock':
        (tmp_path / 'frontend/package-lock.json').write_text('{}')
    if fault in {'omission', 'duplicate'}:
        p = tmp_path / 'docs/licenses/frontend.json'
        d = json.loads(p.read_text())
        if fault == 'omission':
            d['components'].pop()
        else:
            d['components'].append(d['components'][0])
        p.write_text(json.dumps(d))
    if fault in {'text', 'docs_text'}:
        (tmp_path / ('docs/licenses/frontend.txt' if fault == 'text' else 'docs/licenses/documentation.txt')).write_text('altered')
    check = runpy.run_path(str(source / 'scripts/check_licenses.py'))['check']
    if fault:
        with pytest.raises(ValueError):
            check(tmp_path)
    else:
        assert check(tmp_path)['status'] == 'passed'
