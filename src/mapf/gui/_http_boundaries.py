"""Local request limits and explicit HTTP failure classifications."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


async def local_limits(request: Request, call_next: Any) -> Any:
    from urllib.parse import urlparse

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
            "testserver",
        }:
            return JSONResponse(
                {"detail": "This workspace accepts local browser origins only"},
                status_code=403,
            )
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > 16 * 1024 * 1024:
                return JSONResponse(
                    {"detail": "Request exceeds 16 MiB local import limit"},
                    status_code=413,
                )
            chunks.append(chunk)
        request._body = b"".join(chunks)
    return await call_next(request)

async def invalid_input(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": str(exc), "kind": "invalid_input_or_artifact"}, status_code=422
    )

async def missing_resource(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"detail": f"Resource not found: {exc}"}, status_code=404)

async def capacity(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": str(exc), "kind": "local_capacity"}, status_code=429
    )

async def storage_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": str(exc), "kind": "storage_failure"}, status_code=507
    )



def install(app: FastAPI) -> None:
    app.middleware("http")(local_limits)
    app.add_exception_handler(ValueError, invalid_input)
    app.add_exception_handler(KeyError, missing_resource)
    app.add_exception_handler(OverflowError, capacity)
    app.add_exception_handler(OSError, storage_error)
