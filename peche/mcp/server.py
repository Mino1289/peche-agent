"""Serveur MCP — expose les outils de peche-agent à Cursor et autres clients.

Lancement :
    python3 -m peche.mcp                    # stdio (Cursor local)
    python3 -m peche.mcp --transport http   # HTTP streamable (standalone)
    MCP_ENABLED=1 via FastAPI                 # http://host:8000/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

import peche  # charge .env
from peche.agent.schemas import TOOL_SCHEMAS, TOOLS

_ = peche

logger = logging.getLogger("peche.mcp")

server = Server("peche-agent")


def _schema_to_mcp_tool(schema: dict) -> types.Tool:
    return types.Tool(
        name=schema["name"],
        description=schema.get("description", ""),
        inputSchema=schema.get("parameters", {"type": "object", "properties": {}}),
    )


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [_schema_to_mcp_tool(s) for s in TOOL_SCHEMAS]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[types.TextContent]:
    handler = TOOLS.get(name)
    if handler is None:
        raise ValueError(f"Outil inconnu : {name}")
    args = arguments or {}
    try:
        result = handler(**args)
        text = json.dumps(result, ensure_ascii=False, default=str)
    except TypeError as exc:
        raise ValueError(f"Arguments invalides pour {name}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erreur outil %s", name)
        text = json.dumps(
            {"error": f"{type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )
    return [types.TextContent(type="text", text=text)]


def _init_options() -> InitializationOptions:
    return InitializationOptions(
        server_name="peche-agent",
        server_version="0.0.0",
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )


class _StreamableHTTPASGIApp:
    def __init__(self, session_manager: StreamableHTTPSessionManager) -> None:
        self._session_manager = session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._session_manager.handle_request(scope, receive, send)


def create_mcp_http_stack(*, stateless: bool = True):
    """Retourne (asgi_app, session_manager) pour montage sur FastAPI ou Starlette."""
    session_manager = StreamableHTTPSessionManager(app=server, stateless=stateless)
    asgi = _StreamableHTTPASGIApp(session_manager)
    return asgi, session_manager


def create_http_app(*, path: str = "/mcp", stateless: bool = True) -> Starlette:
    asgi, session_manager = create_mcp_http_stack(stateless=stateless)

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with session_manager.run():
            yield

    return Starlette(
        routes=[Route(path, endpoint=asgi)],
        lifespan=lifespan,
    )


async def run_stdio() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, _init_options())


async def run_http(host: str, port: int, *, path: str = "/mcp") -> None:
    import uvicorn

    starlette_app = create_http_app(path=path)
    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="warning",
    )
    await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serveur MCP peche-agent")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("PECHE_MCP_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PECHE_MCP_PORT", "8001")),
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("PECHE_MCP_PATH", "/mcp"),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    if args.transport == "http":
        logger.info("MCP HTTP sur http://%s:%s%s", args.host, args.port, args.path)
        asyncio.run(run_http(args.host, args.port, path=args.path))
    else:
        asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
