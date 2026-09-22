"""Verify pinned notice inventories without network access or executing dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check(root: Path, *, docs: bool = False) -> dict:
    folder = root / 'docs/licenses'
    inventory = json.loads((folder / 'frontend.json').read_text())
    lock_bytes = (root / 'frontend/package-lock.json').read_bytes()
    lock = json.loads(lock_bytes)
    if sha(lock_bytes) != inventory['lock_sha256']:
        raise ValueError('Frontend lock changed; review and regenerate notices')
    expected = {(p, v['version']) for p, v in lock['packages'].items()
                if p and (not v.get('dev') or p == 'node_modules/vite')}
    actual = {(c['package_path'], c['version']) for c in inventory['components']}
    if expected != actual or len(actual) != len(inventory['components']):
        raise ValueError('Frontend notice inventory does not match the locked dependency closure')
    if sha((folder / 'frontend.txt').read_bytes()) != inventory['notices_sha256']:
        raise ValueError('Frontend notice text changed')
    doc = json.loads((folder / 'documentation.json').read_text())
    if sha((folder / 'documentation.txt').read_bytes()) != doc['notices_sha256']:
        raise ValueError('Documentation notice text changed')
    if docs:
        for name, version in doc['installed_versions'].items():
            if distribution(name).version != version:
                raise ValueError(f'Review documentation licenses after upgrading {name}')
        theme = Path(distribution('mkdocs-material').locate_file('material/templates'))
        assets = {str(p.relative_to(theme)): sha(p.read_bytes())
                  for p in (theme / 'assets').rglob('*') if p.is_file()
                  and '/javascripts/lunr/' not in str(p)}
        if assets != doc['material_assets']:
            raise ValueError('Unreviewed documentation theme assets')
    native = json.loads((folder / 'native.json').read_text())
    if not (folder / 'native.txt').read_text().strip() or len(native) != 3:
        raise ValueError('Optional native solver notices missing')
    return {'status': 'passed', 'gui_components': len(actual),
            'documentation_components': len(doc['components']), 'installed_docs_checked': docs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docs', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check(ROOT, docs=args.docs), indent=2))
