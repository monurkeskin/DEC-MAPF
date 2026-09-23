"""Compose the local research workspace without starting workers on import."""

from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from mapf.gui import (
    _http_boundaries,
    _legacy_archives,
    _legacy_benchmarks,
    _legacy_presets,
    _legacy_simulation,
)
from mapf.gui._services import WorkspaceServices
from mapf.gui.api_v1 import router
from mapf.gui.assets import mount_workspace


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    owner = WorkspaceServices(data_dir)
    app = FastAPI(
        lifespan=owner.lifespan,
        title="DEC-MAPF - Research Workspace",
        description="Decentralized MAPF simulation and centralized solver comparisons, independent trajectory validation, replay and experiment analysis.",
        version="0.1.0a2",
    )
    app.state.workspace_services = owner.services
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    _http_boundaries.install(app)
    app.include_router(router(owner.services, owner.experiments))
    dist_dir = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    static_dir = Path(__file__).parent / "static"
    mount_workspace(app, dist_dir, static_dir)
    app.include_router(_legacy_presets.api)
    app.include_router(_legacy_simulation.router(owner.services))
    app.include_router(_legacy_benchmarks.api)
    app.include_router(_legacy_archives.api)
    return app


app = create_app()
