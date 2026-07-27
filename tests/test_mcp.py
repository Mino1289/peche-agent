"""Tests pour peche.mcp.server."""

import asyncio
import json

import pytest

from peche.agent.schemas import TOOL_SCHEMAS
from peche.mcp.server import _schema_to_mcp_tool, handle_call_tool, handle_list_tools


def test_schema_to_mcp_tool():
    schema = TOOL_SCHEMAS[0]
    tool = _schema_to_mcp_tool(schema)
    assert tool.name == schema["name"]
    assert tool.description == schema.get("description", "")
    assert tool.inputSchema == schema.get("parameters")


def test_handle_list_tools_count():
    tools = asyncio.run(handle_list_tools())
    assert len(tools) == len(TOOL_SCHEMAS)


def test_handle_call_tool_unknown():
    with pytest.raises(ValueError, match="inconnu"):
        asyncio.run(handle_call_tool("outil_inexistant", {}))


def test_handle_call_tool_list_zones():
    result = asyncio.run(handle_call_tool("list_zones", {}))
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert isinstance(payload, list)
    assert len(payload) == 34
