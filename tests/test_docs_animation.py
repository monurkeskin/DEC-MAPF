"""The documentation export must preserve playable image assets and their links."""
import importlib.util
import json
import shutil
from pathlib import Path


def test_documentation_stage_retains_animated_assets(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1]
    stage_source = tmp_path / "source"
    spec = importlib.util.spec_from_file_location("documentation_build", source / "scripts/build_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("docs", "examples", "scripts", "tests", "src", ".github", "frontend", "benchmarks"):
        (stage_source / name).mkdir(parents=True)
    for name in ("README.md", "CONTRIBUTING.md", "REPRODUCIBILITY.md", "CHANGELOG.md", "CITATION.cff", "reference.bib", "LICENSE", "THIRD_PARTY_NOTICES.md", "pyproject.toml", "uv.lock", "codemeta.json", ".zenodo.json", "frontend/package-lock.json", "mkdocs.yml", "benchmarks/README.md"):
        shutil.copyfile(source / name, stage_source / name)
    gallery = stage_source / "docs/assets/gallery"
    gallery.mkdir(parents=True)
    payloads = {"replay.gif": b"GIF89a-replay-fixture", "replay.webp": b"RIFF-webp-fixture"}
    for name, data in payloads.items():
        (gallery / name).write_bytes(data)
    (stage_source / "README.md").write_text("[![Replay](docs/assets/gallery/replay.gif)](docs/assets/gallery/replay.webp)\n")
    monkeypatch.setattr(module, "ROOT", stage_source)
    monkeypatch.setattr(module, "STAGING", tmp_path / "built")
    module.stage()
    content = module.STAGING / "content"
    receipt = json.loads((content / "documentation-source.json").read_text())
    for name, data in payloads.items():
        relative = f"docs/assets/gallery/{name}"
        assert (content / relative).read_bytes() == data
        assert relative in receipt["sources"]
    assert "docs/assets/gallery/replay.gif" in (content / "index.md").read_text()
    assert "docs/assets/gallery/replay.webp" in (content / "index.md").read_text()


def test_english_docs_prune_unused_language_bundles_and_reject_unreviewed_languages(tmp_path):
    import runpy

    import pytest
    finalize = runpy.run_path("scripts/build_docs.py")["finalize_site"]
    (tmp_path / "search").mkdir()
    (tmp_path / "assets/javascripts/lunr").mkdir(parents=True)
    (tmp_path / "assets/javascripts/lunr/wordcut.js").write_text("unused language asset")
    index = tmp_path / "search/search_index.json"
    index.write_text('{"config": {"lang": ["en", "ja"]}}')
    with pytest.raises(ValueError, match="licenses"):
        finalize(tmp_path)
    assert (tmp_path / "assets/javascripts/lunr/wordcut.js").exists()
    index.write_text('{"config": {"lang": ["en"]}}')
    finalize(tmp_path)
    assert not (tmp_path / "assets/javascripts/lunr").exists()
