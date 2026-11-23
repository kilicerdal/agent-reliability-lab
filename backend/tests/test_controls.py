import anyio

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
    result = anyio.run(capture)
    assert all(result["checks"].values()), result["checks"]
