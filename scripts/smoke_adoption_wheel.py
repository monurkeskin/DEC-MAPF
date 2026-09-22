"""Qualify the public API, project scaffold and capsules against an installed core wheel."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    import mapf
    from mapf.api import API_VERSION, create_study
    assert 'site-packages' in Path(mapf.__file__).parts, mapf.__file__
    assert importlib.util.find_spec('fastapi') is None
    assert API_VERSION == '1'
    source = Path(__file__).resolve().parents[1]
    environment = {k:v for k,v in os.environ.items() if k != 'PYTHONPATH'}
    environment.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    receipts = {}
    with tempfile.TemporaryDirectory(prefix='decmapf-adoption-wheel-') as directory:
        root = Path(directory)
        shutil.copytree(source/'examples/capsules', root/'capsules')
        for name in ('negotiation', 'settings'):
            result = subprocess.run([sys.executable, str(root/'capsules'/name/'run.py'), '--output', str(root/name)],
                                    cwd=root, env=environment, capture_output=True, text=True, timeout=150, check=False)
            if result.returncode:
                raise RuntimeError(f'{name}: {result.stdout}\n{result.stderr}')
            receipt = json.loads((root/name/'receipt.json').read_text())
            manifest = json.loads((root/name/'manifest.json').read_text())
            assert manifest['provenance']['source_origin'] == 'installed-package'
            assert manifest['provenance']['git_commit'] == 'unavailable'
            assert receipt['summary']['successful'] == receipt['summary']['planned']
            receipts[name] = receipt
        create_study(root/'my-study')
        for script in ('run.py', 'analyze.py'):
            result = subprocess.run([sys.executable,str(root/'my-study'/script)],cwd=root,env=environment,
                                    capture_output=True,text=True,timeout=150, check=False)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
        receipts['scaffold_card'] = json.loads((root/'my-study/outputs/experiment-card.json').read_text())
        assert receipts['scaffold_card']['outcomes']['valid_solutions'] == 4
        # A real module-scope existing-solver extension is reconstructed in spawned workers.
        extension=root/'registered.py'
        shutil.copyfile(source/'examples/05_registered_solver_study.py',extension)
        result = subprocess.run([sys.executable,str(extension),'--workspace',str(root/'extension')],cwd=root,env=environment,
                                capture_output=True,text=True,timeout=45, check=False)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        receipts['registered_existing_solver']=json.loads(result.stdout)
        assert receipts['registered_existing_solver']['successful']==1
    print(json.dumps({'status':'passed','version':mapf.__version__,'module':mapf.__file__,'fastapi_installed':False,
                      'fixtures':25,'receipts':receipts,'scope':'Small installed-package workflow qualification, not article results'},indent=2))


if __name__ == '__main__':
    main()
