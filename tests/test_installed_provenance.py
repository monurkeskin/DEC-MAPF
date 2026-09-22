"""An installed package must not claim its enclosing project's Git revision."""
import subprocess

from mapf.application import plans


def test_installed_package_ignores_unrelated_enclosing_git_repository(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("Unrelated host project\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Host project"], check=True)
    installed = tmp_path / ".venv/lib/python3.12/site-packages/mapf/application/plans.py"
    installed.parent.mkdir(parents=True)
    installed.write_text("# installed fixture\n")
    monkeypatch.setattr(plans, "__file__", str(installed))
    receipt = plans.provenance()
    assert receipt["git_commit"] == "unavailable"
    assert receipt["working_tree_dirty"] is None
    assert receipt["source_origin"] == "installed-package"
    assert receipt["source_files"] == {"application/plans.py": receipt["source_files"]["application/plans.py"]}
