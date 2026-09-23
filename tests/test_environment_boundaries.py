"""Optional dependencies and installed GUI assets have explicit readiness states."""

import importlib.metadata
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mapf.application import diagnostics
from mapf.gui.assets import mount_workspace


def test_diagnostic_unknown_component_is_rejected():
    with pytest.raises(ValueError, match="Unknown diagnostic"):
        diagnostics.diagnose(required=["typo"])


def test_loaded_module_without_spec_is_unavailable_not_an_internal_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "diagnostic_placeholder", types.ModuleType("diagnostic_placeholder"))
    assert not diagnostics.module_available("diagnostic_placeholder")
    assert not diagnostics.module_available("absent_decmapf_dependency_943")


def test_missing_assets_and_distribution_are_reported_without_installing(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "__file__", str(tmp_path / "src/mapf/application/diagnostics.py"))

    def absent(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(diagnostics.importlib.metadata, "version", absent)
    report = diagnostics.diagnose(required=["gui"])
    assert report["status"] == "error"
    assert report["package_version"] is None
    assert "gui" in report["missing_requirements"]
    assert not report["gui_assets_available"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("valid", [True, False])
def test_required_native_binary_identity_is_checked_and_failure_is_visible(monkeypatch, valid):
    class Profile:
        solver_id, family, qualification_scope = "fixture-native", "eecbs", "finite fixture"

        def verify_binary(self):
            if not valid:
                raise OSError("native binary was replaced")

    monkeypatch.setattr(diagnostics, "native_profiles", lambda: [Profile()])
    report = diagnostics.diagnose(required=["native"])
    assert report["components"]["native"]["available"] is valid
    if valid:
        assert report["native_profiles"][0]["identity_verified"]
    else:
        assert report["native_error"] == "native binary was replaced"
        assert report["status"] == "error"


def test_gui_package_exports_only_the_lazy_factory():
    import mapf.gui as package
    from mapf.gui.app import create_app

    assert package.create_app is create_app
    with pytest.raises(AttributeError, match="has no attribute"):
        _ = package.unknown


@pytest.mark.parametrize("layout", ["unbuilt", "legacy", "wheel"])
def test_gui_asset_fallback_and_notice_availability(tmp_path, layout):
    static, development = tmp_path / "static", tmp_path / "frontend"
    static.mkdir()
    if layout == "legacy":
        (static / "index.html").write_text("<h1>Fallback workspace</h1>")
    if layout == "wheel":
        bundle = static / "workspace"
        (bundle / "assets").mkdir(parents=True)
        (bundle / "index.html").write_text("<h1>Bundled workspace</h1>")
        (bundle / "assets/app.js").write_text("console.log('fixture')")
    app = FastAPI()
    mount_workspace(app, development, static)
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        expected = {"unbuilt": "Build the GUI", "legacy": "Fallback workspace", "wheel": "Bundled workspace"}[layout]
        assert expected in response.text
        assert client.get("/THIRD_PARTY_NOTICES.txt").status_code == 404
        assert client.get("/license-inventory.json").status_code == 404
        if layout == "wheel":
            assert client.get("/assets/app.js").status_code == 200
