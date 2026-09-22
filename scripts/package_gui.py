"""Copy a successfully built offline frontend into wheel package data."""

import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "frontend/dist"
if not all((source / name).is_file() for name in ("index.html", "THIRD_PARTY_NOTICES.txt", "license-inventory.json")):
    raise SystemExit("Build frontend with npm ci && npm run build first (including license notices)")
target = root / "src/mapf/gui/static/workspace"
if target.exists():
    shutil.rmtree(target)  # Only this script-owned generated package tree.
shutil.copytree(source, target)
# Setuptools can otherwise retain obsolete content-hashed assets from a previous
# build/lib tree and include them in a later wheel despite a clean source target.
staged = root / "build/lib/mapf/gui/static/workspace"
if staged.exists():
    shutil.rmtree(staged)  # The corresponding generated build staging tree only.
print(target)
