"""API FastAPI map-first : catalogue, OGC proxy, chat SSE, static SPA."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from peche import DOTENV_LOADED  # noqa: F401 — charge .env
from peche.api.routes import (
    catalog,
    chat,
    conversations,
    features,
    health,
    live,
    ogc,
    plans,
    point,
    zones,
)

WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

_HTML_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


def _mcp_enabled() -> bool:
    return os.environ.get("MCP_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


class ImmutableStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


class SelectiveGZipMiddleware:
    """GZip sauf pour /mcp (streaming MCP)."""

    def __init__(self, app: ASGIApp, minimum_size: int = 500) -> None:
        self.app = app
        self._gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path") or ""
            if path == "/mcp" or path.startswith("/mcp/"):
                await self.app(scope, receive, send)
                return
        await self._gzip(scope, receive, send)


def create_app() -> FastAPI:
    mcp_asgi = None
    mcp_session_manager = None
    if _mcp_enabled():
        from peche.mcp.server import create_mcp_http_stack

        mcp_asgi, mcp_session_manager = create_mcp_http_stack()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if mcp_session_manager is not None:
            async with mcp_session_manager.run():
                yield
        else:
            yield

    app = FastAPI(title="peche-agent", version="0.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SelectiveGZipMiddleware, minimum_size=500)

    app.include_router(catalog.router)
    app.include_router(ogc.router)
    app.include_router(features.router)
    app.include_router(live.router)
    app.include_router(zones.router)
    app.include_router(plans.router)
    app.include_router(point.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(health.router)

    if mcp_asgi is not None:
        app.mount("/mcp", mcp_asgi)

    if WEB_DIST.is_dir():
        assets = WEB_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", ImmutableStaticFiles(directory=assets), name="assets")

        @app.get("/")
        def spa_index():
            return FileResponse(WEB_DIST / "index.html", headers=_HTML_CACHE)

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            if (
                full_path.startswith("api/")
                or full_path == "api"
                or full_path == "mcp"
                or full_path.startswith("mcp/")
            ):
                from fastapi import HTTPException

                raise HTTPException(status_code=404)
            candidate = WEB_DIST / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(WEB_DIST / "index.html", headers=_HTML_CACHE)

    return app


app = create_app()
