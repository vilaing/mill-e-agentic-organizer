"""MCP server wrapper around the same tools agent.py uses.

Exposes every assignment/points/recruiting/calendar/email tool over the
Model Context Protocol, so any MCP-compatible client (Claude Desktop, another
agent, etc.) can use them -- not just this repo's own tool-use loop.

Reuses the functions and name/description metadata already defined in
src/tools/*.py (TOOL_SCHEMAS + DISPATCH) directly -- no duplicate wrapper
functions to keep in sync. Input schemas are inferred by the MCP SDK from
each function's type hints rather than the hand-written JSON schemas in
TOOL_SCHEMAS, so a couple of string fields that are enums for Claude's native
tool use (e.g. reward_style, recruiting stage) show up as plain strings here
-- the description text still documents the valid values.

Run directly:
    python -m src.mcp_server
Or point an MCP client's config at this module, e.g. for Claude Desktop:
    {
      "mcpServers": {
        "student-agent": {
          "command": "/path/to/venv/bin/python",
          "args": ["-m", "src.mcp_server"],
          "cwd": "/path/to/student-agent"
        }
      }
    }
"""
from mcp.server.mcpserver import MCPServer

from src.tools import db_tool, calendar_tool, gmail_tool

mcp = MCPServer(
    "student-agent",
    description="Assignment tracker, recruiting pipeline, points/rewards, calendar, and email for a college student.",
)

for _module in (db_tool, calendar_tool, gmail_tool):
    for _schema in _module.TOOL_SCHEMAS:
        _fn = _module.DISPATCH[_schema["name"]]
        mcp.add_tool(_fn, name=_schema["name"], description=_schema["description"])


if __name__ == "__main__":
    mcp.run()
