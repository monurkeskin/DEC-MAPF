"""GUI distribution selection must tolerate incomplete development builds."""
from pathlib import Path

from fastapi.testclient import TestClient

import mapf.gui.app as gui


def tree(tmp_path, monkeypatch):
    module = tmp_path / "src/mapf/gui/app.py"
    module.parent.mkdir(parents=True)
    monkeypatch.setattr(gui, "__file__", str(module))
    packaged = module.parent / "static/workspace"
    packaged.mkdir(parents=True)
    (packaged / "index.html").write_text("<title>Installed workspace</title>")
    development = tmp_path / "frontend/dist"
    development.mkdir(parents=True)
    return development, packaged


def test_empty_development_directory_uses_installed_workspace(tmp_path, monkeypatch):
    tree(tmp_path, monkeypatch)
    with TestClient(gui.create_app(tmp_path / "data")) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Installed workspace" in response.text


def test_complete_development_build_takes_precedence(tmp_path, monkeypatch):
    development, _ = tree(tmp_path, monkeypatch)
    (development / "index.html").write_text("<title>Development workspace</title>")
    with TestClient(gui.create_app(tmp_path / "data")) as client:
        assert "Development workspace" in client.get("/").text


def test_notices_follow_selected_bundle_and_do_not_expose_arbitrary_files(tmp_path, monkeypatch):
    _, packaged = tree(tmp_path, monkeypatch)
    (packaged / "THIRD_PARTY_NOTICES.txt").write_text("Required attribution")
    (packaged / "license-inventory.json").write_text('{"components": []}')
    Path(packaged / "secret.txt").write_text("not public")
    with TestClient(gui.create_app(tmp_path / "data")) as client:
        assert client.get("/THIRD_PARTY_NOTICES.txt").text == "Required attribution"
        assert client.get("/license-inventory.json").json() == {"components": []}
        assert client.get("/secret.txt").status_code == 404


def test_unbuilt_source_falls_back_without_exposing_missing_assets(tmp_path, monkeypatch):
    _, packaged = tree(tmp_path, monkeypatch)
    (packaged / "index.html").unlink()
    (packaged.parent / "index.html").write_text("Legacy local dashboard")
    with TestClient(gui.create_app(tmp_path / "data")) as client:
        assert "Legacy local dashboard" in client.get("/").text
        assert client.get("/THIRD_PARTY_NOTICES.txt").status_code == 404
