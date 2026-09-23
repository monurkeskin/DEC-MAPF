"""Read-only researcher environment checks; no supervisor or optional GUI imports."""
from __future__ import annotations

import importlib.metadata
import importlib.util
import platform
from pathlib import Path
from typing import Any

from mapf.application.native_solvers import native_profiles
from mapf.application.runs import RunRepository

COMPONENTS = {
    "core": ("pydantic", "rfc8785"),
    "gui": ("fastapi", "uvicorn", "polars"),
    "analysis": ("numpy", "polars", "matplotlib", "pyarrow"),
    "resources": ("psutil",),
}


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def diagnose(*, workspace: str | Path | None = None, required: list[str] | None = None) -> dict[str, Any]:
    requirements = sorted({"core", *(required or [])})
    if set(requirements) - {*COMPONENTS, "native"}:
        raise ValueError("Unknown diagnostic component")
    package_root = Path(__file__).resolve().parents[1]
    packaged_assets = package_root / "gui/static/workspace/index.html"
    checkout_assets = package_root.parent.parent / "frontend/dist/index.html"
    components = {name: {"available": all(module_available(module) for module in modules),
        "missing_modules": [module for module in modules if not module_available(module)]}
        for name, modules in COMPONENTS.items()}
    assets = packaged_assets.is_file() or checkout_assets.is_file()
    if not assets:
        components["gui"]["available"] = False
    native: list[dict[str, Any]] = []
    native_error = None
    try:
        for profile in native_profiles():
            info: dict[str, Any] = {"solver_id": profile.solver_id, "family": profile.family,
                "qualification_scope": profile.qualification_scope, "identity_verified": False}
            if "native" in requirements:
                profile.verify_binary()
                info["identity_verified"] = True
            native.append(info)
    except (ValueError, OSError) as exc:
        native_error = str(exc)
    components["native"] = {"available": bool(native) and native_error is None,
                            "missing_modules": []}
    version = None
    try:
        version = importlib.metadata.version("dec-mapf")
    except importlib.metadata.PackageNotFoundError:
        pass
    workspace_info: dict[str, Any] | None = None
    if workspace is not None:
        try:
            repository = RunRepository.open_existing(workspace)
            with repository.connect() as db:
                workspace_info = {"path": str(repository.base_dir), "schema_version": repository.inspect_schema(),
                    "jobs": db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                    "runs": db.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
                    "mode": "read-only; owner not acquired"}
        except (OSError, ValueError) as exc:
            workspace_info = {"error": str(exc)}
    missing = [name for name in requirements if not components[name]["available"]]
    return {"schema_version": "doctor-1", "status": "error" if missing or (workspace_info and "error" in workspace_info) else "ok",
        "required": requirements, "missing_requirements": missing, "package_version": version,
        "python": platform.python_version(), "platform": platform.platform(), "components": components,
        "gui_assets_available": assets, "native_profiles": native, "native_error": native_error,
        "workspace": workspace_info,
        "scope": "Environment readiness only; no solver executed and no scientific correctness certification"}
