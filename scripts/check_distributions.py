"""Inspect the source archive and its wheel without importing the source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REQUIRED_SOURCE = {
    "pyproject.toml",
    "uv.lock",
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "docs/LICENSING.md",
    "docs/licenses/frontend.txt",
    "docs/licenses/frontend.json",
    "docs/licenses/documentation.txt",
    "docs/licenses/documentation.json",
    "docs/licenses/native.txt",
    "CITATION.cff",
    "benchmarks/suites/regression_core.json",
    "benchmarks/run_profiling_suite.py",
    "mkdocs.yml",
    "docs/METRICS.md",
    "docs/PUBLIC-API.md",
    "examples/capsules/negotiation/run.py",
    "docs/INSTALLATION.md",
    "examples/negotiation-tutorial.json",
    "frontend/src/App.tsx",
    "frontend/package-lock.json",
}
REQUIRED_WHEEL = {
    "mapf/api.py",
    "mapf/conformance.py",
    "mapf/study_cli.py",
    "mapf/application/studies.py",
    "mapf/application/narratives.py",
    "mapf/application/capsules.py",
    "mapf/py.typed",
    "mapf/cli.py",
    "mapf/doctor_cli.py",
    "mapf/gui/static/workspace/index.html",
    "mapf/gui/static/workspace/THIRD_PARTY_NOTICES.txt",
    "mapf/gui/static/workspace/license-inventory.json",
}

REPORT_TEMPLATES = {
    "mapf/analytics/templates/trajectory.html",
    "mapf/analytics/templates/diagnostics.html",
}
REQUIRED_WHEEL |= REPORT_TEMPLATES
REQUIRED_SOURCE |= {"src/" + name for name in REPORT_TEMPLATES}


def read_source(sdist: Path) -> dict[str, bytes]:
    with tarfile.open(sdist, "r:gz") as archive:
        source = {}
        for member in archive.getmembers():
            if member.isfile():
                stream = archive.extractfile(member)
                assert stream is not None
                source[member.name.partition("/")[2]] = stream.read()
    return source


def read_wheel(wheel: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(wheel) as archive:
        installed = {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
    return installed


def research_or_local_path(name: str) -> bool:
    return (
        name.startswith(
            ("benchmarks/data/", "benchmarks/results/", "assets/", "docs/releases/")
        )
        or name == "benchmarks/historical-artifacts.json"
        or name.endswith((".sqlite", ".db", ".xlsx", ".parquet", ".jsonl"))
    )


def check_public_contents(source: dict, installed: dict) -> None:
    forbidden = [name for name in source if research_or_local_path(name)]
    if forbidden:
        raise ValueError(
            f"Distribution contains research data or local state: {sorted(forbidden)}"
        )
    patterns = runpy.run_path(str(Path(__file__).with_name("public_export.py")))[
        "PATTERNS"
    ]
    for name, data in {**source, **installed}.items():
        if any(pattern.search(data) for pattern in patterns):
            raise ValueError(
                f"Distribution contains content outside the public baseline: {name}"
            )


def check_required_files(source: dict, installed: dict) -> None:
    missing = REQUIRED_SOURCE - source.keys()
    missing |= REQUIRED_WHEEL - installed.keys()
    if missing:
        raise ValueError(f"Distribution is incomplete: {sorted(missing)}")


def packaged_file(name: str, prefix: str = "mapf/") -> bool:
    if not name.startswith(prefix):
        return False
    return (
        name.endswith((".py", "py.typed"))
        or "/gui/static/" in name
        or "/analytics/templates/" in name
    )


def check_payload_identity(packaged: dict, installed: dict) -> None:
    for name, data in packaged.items():
        if installed.get(name) != data:
            raise ValueError(f"Wheel differs from source distribution: {name}")


def check_packaged_inventory(packaged: dict, installed: dict) -> None:
    for name in installed:
        if packaged_file(name) and name not in packaged:
            raise ValueError(f"Wheel contains stale or untracked packaged file: {name}")


def javascript_assets(packaged: dict) -> list[str]:
    assets = [name for name in packaged if "/workspace/assets/" in name]
    if not assets or not any(name.endswith(".js") for name in assets):
        raise ValueError("Built GUI JavaScript assets are missing")
    return assets


def matching_package(source: dict, installed: dict) -> tuple[dict, list]:
    packaged = {
        key.removeprefix("src/"): value
        for key, value in source.items()
        if packaged_file(key, "src/mapf/")
    }
    check_payload_identity(packaged, installed)
    check_packaged_inventory(packaged, installed)
    return packaged, javascript_assets(packaged)


def inspect_distribution_pair(sdist: Path, wheel: Path) -> dict:
    source, installed = read_source(sdist), read_wheel(wheel)
    check_public_contents(source, installed)
    check_required_files(source, installed)
    packaged, assets = matching_package(source, installed)
    return {
        "status": "passed",
        "scope": "Distribution completeness and byte identity; installed behavior is qualified separately",
        "matched_source_and_asset_files": len(packaged),
        "gui_asset_files": len(assets),
        "distributions": [
            {
                "file": p.name,
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in (sdist, wheel)
        ],
    }


def archived_documentation(sdist: Path) -> dict:
    # Qualify documentation from the archive itself: a passing checkout link
    # check alone cannot reveal missing example maps or contribution templates.
    with tempfile.TemporaryDirectory(prefix="decmapf-sdist-") as directory:
        with tarfile.open(sdist, "r:gz") as archive:
            archive.extractall(directory, filter="data")
        roots = list(Path(directory).iterdir())
        if len(roots) != 1 or not roots[0].is_dir():
            raise ValueError("Source archive must contain a single project directory")
        result = subprocess.run(
            [sys.executable, str(roots[0] / "scripts/check_documentation.py")],
            cwd=roots[0],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise ValueError(
                "Archived documentation check failed: " + result.stdout + result.stderr
            )
        return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    sources, wheels = (
        list(args.directory.glob("*.tar.gz")),
        list(args.directory.glob("*.whl")),
    )
    if len(sources) != 1 or len(wheels) != 1:
        raise SystemExit(
            "Use a clean output directory with exactly one source archive and one wheel"
        )
    receipt = inspect_distribution_pair(sources[0], wheels[0])
    receipt["source_documentation"] = archived_documentation(sources[0])
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
