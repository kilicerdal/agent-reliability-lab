import os

import anyio
import pytest

from backend.controls.evidence import capture
from backend.controls.server import CATALOG, REQUEST


def test_catalog_has_only_scoped_tools():
    assert {tool.name for tool in CATALOG} == {
        "read_logs",
        "read_deployments",
        "read_health",
        "read_queue",
        REQUEST,
    }
    assert all(
        tool.input_schema["properties"] == {}
        and not tool.input_schema["additionalProperties"]
        for tool in CATALOG
    )


def test_mcp_scope_and_operator_approval(database):
    if "LAB_MCP_DSN" not in os.environ:
        pytest.skip("MCP integration requires LAB_MCP_DSN")
    result = anyio.run(capture)
    assert all(result["checks"].values()), result["checks"]
