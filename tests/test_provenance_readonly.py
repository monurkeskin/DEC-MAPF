"""Capturing run provenance must never refresh or lock a repository index."""
import os
import subprocess

from mapf.application import plans


def test_provenance_leaves_git_index_bytes_unchanged(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    source = tmp_path / "src" / "mapf" / "application" / "plans.py"
    source.parent.mkdir(parents=True)
    source.write_text("# isolated provenance fixture\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "dec-mapf"\n')
    subprocess.run(["git", "add", "src"], cwd=tmp_path, check=True)
    index = tmp_path / ".git" / "index"
    before = index.read_bytes()
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2000000000))
    monkeypatch.setattr(plans, "__file__", str(source))
    receipt = plans.provenance()
    assert receipt["working_tree_dirty"]
    assert receipt["source_files"]
    assert index.read_bytes() == before
    assert not (tmp_path / ".git" / "index.lock").exists()
