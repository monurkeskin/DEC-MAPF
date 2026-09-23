"""Packaging gates reject absent GUI assets and stale wheel contents."""

import io
import runpy
import tarfile
import zipfile

import pytest


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "stale",
        "changed",
        "missing",
        "raw",
        "context",
        "history",
        "private_commit",
        "notices",
        "template",
    ],
)
def test_distribution_identity_and_missing_content(tmp_path, fault):
    check = runpy.run_path("scripts/check_distributions.py")[
        "inspect_distribution_pair"
    ]
    files = {
        name: b"fixture"
        for name in [
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
            "src/mapf/api.py",
            "src/mapf/conformance.py",
            "src/mapf/study_cli.py",
            "src/mapf/application/studies.py",
            "src/mapf/application/narratives.py",
            "src/mapf/application/capsules.py",
            "docs/INSTALLATION.md",
            "examples/negotiation-tutorial.json",
            "frontend/src/App.tsx",
            "frontend/package-lock.json",
            "src/mapf/analytics/templates/trajectory.html",
            "src/mapf/analytics/templates/diagnostics.html",
            "src/mapf/py.typed",
            "src/mapf/cli.py",
            "src/mapf/doctor_cli.py",
            "src/mapf/gui/static/workspace/THIRD_PARTY_NOTICES.txt",
            "src/mapf/gui/static/workspace/license-inventory.json",
            "src/mapf/gui/static/workspace/index.html",
            "src/mapf/gui/static/workspace/assets/index.js",
        ]
    }
    if fault == "notices":
        del files["src/mapf/gui/static/workspace/THIRD_PARTY_NOTICES.txt"]
    if fault == "raw":
        files["benchmarks/results/table.csv"] = b"observations"
    if fault == "context":
        files["README.md"] = b"co-" + b"author preview"
    if fault == "history":
        files["README.md"] = b"## Version " + b"99: obsolete development heading"
    if fault == "private_commit":
        files["docs/provenance.json"] = b'{"git_commit": "' + b"a" * 40 + b'"}'
    source, wheel = tmp_path / "fixture.tar.gz", tmp_path / "fixture.whl"
    with tarfile.open(source, "w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo("fixture/" + name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in files.items():
            if fault == "template" and name.endswith("diagnostics.html"):
                continue
            if not name.startswith("src/") or (
                fault == "missing" and name.endswith("index.html")
            ):
                continue
            archive.writestr(
                name.removeprefix("src/"),
                b"changed" if fault == "changed" and name.endswith("cli.py") else data,
            )
        if fault == "stale":
            archive.writestr("mapf/gui/static/workspace/assets/old.js", b"stale")
    if fault:
        with pytest.raises(ValueError):
            check(source, wheel)
    else:
        assert check(source, wheel)["status"] == "passed"
