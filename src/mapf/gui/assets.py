"""Serve the selected GUI bundle and its accompanying license notices."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles


def mount_workspace(app: FastAPI, development: Path, static: Path) -> None:
    """Prefer a built development index, then the wheel's bundled workspace."""
    bundle = next((p for p in (development, static / "workspace")
                   if (p / "index.html").is_file()), None)
    if bundle is not None and (bundle / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(bundle / "assets")), name="assets")

    @app.get("/", response_class=HTMLResponse)
    async def serve_index() -> Response:
        index = (bundle or static) / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse("<h1>Build the GUI with npm ci and npm run build in frontend/.</h1>")

    def notice_response(name: str) -> FileResponse:
        if bundle is None or not (bundle / name).is_file():
            raise HTTPException(status_code=404, detail="Notice not available in this build")
        return FileResponse(bundle / name)

    @app.get("/THIRD_PARTY_NOTICES.txt", include_in_schema=False)
    async def notices() -> FileResponse:
        return notice_response("THIRD_PARTY_NOTICES.txt")

    @app.get("/license-inventory.json", include_in_schema=False)
    async def inventory() -> FileResponse:
        return notice_response("license-inventory.json")
