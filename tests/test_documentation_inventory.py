"""The documentation gate must cover shipped guides, including nested READMEs."""

import runpy
from pathlib import Path


def test_inventory_covers_exported_markdown_and_ignores_local_outputs(tmp_path):
    checker = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/check_documentation.py")
    )
    documents = checker["documents_to_check"]
    documents.__globals__["ROOT"] = tmp_path
    public = {
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "benchmarks/README.md",
        "frontend/README.md",
        "docs/README.md",
        "src/mapf/application/README.md",
        "examples/nested/README.md",
        ".github/pull_request_template.md",
    }
    local = {
        "runs/draft.md",
        ".venv/README.md",
        "frontend/node_modules/dependency/README.md",
    }
    for name in public | local:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Fixture\n")
    assert {path.relative_to(tmp_path).as_posix() for path in documents()} == public
