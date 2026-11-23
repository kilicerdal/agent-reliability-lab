"""Local MCP server bound by its launcher to one synthetic experiment."""

import argparse
import json
import os
from uuid import UUID

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
from psycopg import IntegrityError

from backend.lab.tools import TOOLS, dispatch

from .approval import request_restart

REQUEST = "request_worker_restart"
DEFINITIONS = [
    *TOOLS,
    {
        "type": "function",
        "name": REQUEST,
        "description": "Request operator review of a worker restart for this experiment. This cannot approve or run a restart.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
]
CATALOG = [
    Tool(
        name=tool["name"],
        description=tool["description"],
        input_schema=tool["parameters"],
    )
    for tool in DEFINITIONS
]
NAMES = {tool.name for tool in CATALOG}


def build_server(experiment):
    async def list_tools(context, params):
        return ListToolsResult(tools=CATALOG)

    async def call_tool(context, params):
        if params.name not in NAMES or params.arguments:
            return CallToolResult(
                is_error=True,
                content=[TextContent(type="text", text="Tool or arguments denied.")],
            )
        try:
            if params.name == REQUEST:
                result = await anyio.to_thread.run_sync(request_restart, experiment)
            else:
                result = await anyio.to_thread.run_sync(
                    dispatch, params.name, {}, experiment
                )
        except IntegrityError:
            return CallToolResult(
                is_error=True,
                content=[TextContent(type="text", text="Experiment unavailable.")],
            )
        return CallToolResult(
            structured_content=result,
            content=[TextContent(type="text", text=json.dumps(result))],
        )

    return Server(
        "Agent Reliability Lab",
        version="3.0.0",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve(experiment):
    async with stdio_server() as (reader, writer):
        server = build_server(experiment)
        await server.run(reader, writer, server.create_initialization_options())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", type=UUID)
    args = parser.parse_args()
    # The MCP process receives only its limited DSN from the trusted launcher.
    os.environ["LAB_READER_DSN"] = os.environ["LAB_MCP_DSN"]
    anyio.run(serve, str(args.experiment))


if __name__ == "__main__":
    main()
