"""Create a clean source snapshot from a committed revision, without Git history.

This command writes local files only. It neither creates a remote repository nor
changes repository visibility. Raw results, machine state and legacy run scripts
are outside the explicit export boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

ROOT_FILES = frozenset({
    '.gitattributes', '.gitignore', '.zenodo.json', 'CHANGELOG.md', 'CITATION.cff', 'CONTRIBUTING.md',
    'LICENSE', 'THIRD_PARTY_NOTICES.md', 'MANIFEST.in', 'Makefile', 'README.md', 'REPRODUCIBILITY.md',
    'codemeta.json', 'mkdocs.yml', 'pyproject.toml', 'reference.bib', 'run_dashboard.py', 'uv.lock',
})
SOURCE_ROOTS = frozenset({'src', 'tests', 'frontend', 'docs', 'examples', 'scripts', '.github'})
BENCHMARK_FILES = frozenset({
    'benchmarks/README.md',
    'benchmarks/suites/regression_core.json', 'benchmarks/run_profiling_suite.py',
})
FORBIDDEN_PARTS = frozenset({
    '.git', '.venv', 'node_modules', '__pycache__', '.cache', '.docs-build',
    'test-results', 'playwright-report', 'dist', 'build', 'runs', 'outputs',
})
PATTERNS = (
    re.compile(rb'co[- ]?author\s+(?:preview|review)', re.IGNORECASE),
    re.compile(rb'prospective\s+co[- ]?authors?', re.IGNORECASE),
    re.compile(rb'/Users/[A-Za-z0-9._-]+/'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(rb'^\s*#{1,6}\s+(?:Version\s+\d+|Engineering\s+revision\s+\d+|Earlier\s+development\s+identifiers)\b', re.IGNORECASE | re.MULTILINE),
    re.compile(rb'modern-python-v\d+-[a-z-]+'),
    re.compile(rb'"(?:git_commit|source_commit)"\s*:\s*"[a-f0-9]{40}"'),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exportable(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or any(p in FORBIDDEN_PARTS for p in path.parts):
        return False
    if path.suffix in {'.sqlite', '.db', '.parquet', '.xlsx', '.jsonl', '.gz', '.pem', '.key'}:
        return False
    if path.name.startswith('.env'):
        return False
    if name.startswith('docs/releases/'):
        return False
    return name in ROOT_FILES or name in BENCHMARK_FILES or (len(path.parts) > 1 and path.parts[0] in SOURCE_ROOTS)


def check_payloads(payloads: dict[str, bytes]) -> dict:
    """Reject known private material without printing matched content."""
    errors = []
    for name, data in payloads.items():
        if not exportable(name):
            errors.append(f'excluded path: {name}')
        if any(pattern.search(data) for pattern in PATTERNS):
            errors.append(f'content requires review: {name}')
    if errors:
        raise ValueError('; '.join(errors))
    return {'files': len(payloads), 'bytes': sum(map(len, payloads.values())), 'status': 'passed'}


def export_snapshot(source: Path, destination: Path, revision: str = 'HEAD') -> dict:
    """Read immutable Git objects; never copy untracked files or follow symlinks."""
    if destination.exists():
        raise ValueError('Destination must not exist; preserve earlier candidates')
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', f'{revision}^{{commit}}'], cwd=source, text=True).strip()
    listing = subprocess.check_output(['git', 'ls-tree', '-rz', commit], cwd=source)
    entries = {}
    for item in listing.split(b'\0'):
        if not item:
            continue
        header, path = item.split(b'\t', 1)
        mode, kind, _ = header.decode().split()
        name = path.decode('utf-8')
        if exportable(name):
            if kind != 'blob' or mode not in {'100644', '100755'}:
                raise ValueError(f'Export requires regular tracked files: {name}')
            entries[name] = mode
    if 'pyproject.toml' not in entries or 'src/mapf/cli.py' not in entries:
        raise ValueError('Not a complete DEC-MAPF source tree')
    archive_bytes = subprocess.check_output(['git', 'archive', '--format=tar', commit, '--', *sorted(entries)], cwd=source)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:') as archive:
        payloads = {}
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile() or member.name not in entries:
                raise ValueError(f'Unexpected archive entry: {member.name}')
            stream = archive.extractfile(member)
            assert stream is not None
            payloads[member.name] = stream.read()
    if payloads.keys() != entries.keys():
        raise ValueError('Archive does not contain the selected committed files')
    receipt = check_payloads(payloads)
    files = {name: {'sha256': digest(data), 'mode': entries[name]} for name, data in sorted(payloads.items())}
    manifest = {'schema': 'decmapf-source-export-1',
                'content_sha256': digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()),
                'files': files,
                'scope': 'Source snapshot; no Git history, raw results, local workspaces or credentials',
                'audit': receipt}
    destination.mkdir(parents=True)
    for name, data in payloads.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(int(entries[name][-3:], 8))
    (destination / 'PUBLICATION-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    # The caller can retain the development revision in its private receipt.
    # Only content checksums are written into the distributable manifest.
    return {**manifest, 'source_commit': commit}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--revision', default='HEAD')
    args = parser.parse_args()
    manifest = export_snapshot(args.source, args.destination, args.revision)
    print(json.dumps({'source_commit': manifest['source_commit'], **manifest['audit']}, indent=2))


if __name__ == '__main__':
    main()
