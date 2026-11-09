"""Starts the real MCP server and speaks the protocol to it over stdio."""
import json
import os
import subprocess
import sys
import threading

import pytest

from src import agent

_TIMEOUT_SECONDS = 30


class McpSession:
    def __init__(self, db_path):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "src.mcp_server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env={**os.environ, "DB_PATH": str(db_path)},
        )
        self.watchdog = threading.Timer(_TIMEOUT_SECONDS, self.process.kill)
        self.watchdog.start()
        self.next_id = 0

    def _write(self, message):
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        self.process.stdin.flush()

    def request(self, method, params=None):
        self.next_id += 1
        self._write({"id": self.next_id, "method": method, "params": params or {}})
        for line in self.process.stdout:
            message = json.loads(line)
            if message.get("id") == self.next_id:
                return message["result"]
        raise AssertionError("The MCP server closed without responding.")

    def notify(self, method):
        self._write({"method": method})

    def close(self):
        self.watchdog.cancel()
        self.process.stdin.close()
        self.process.terminate()
        self.process.wait()


@pytest.fixture
def session(db):
    mcp = McpSession(db)
    mcp.initialized = mcp.request("initialize", {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1"},
    })
    mcp.notify("notifications/initialized")
    yield mcp
    mcp.close()


def test_handshake_identifies_the_server(session):
    assert session.initialized["serverInfo"]["name"] == "student-agent"
    assert "tools" in session.initialized["capabilities"]


def test_mcp_exposes_exactly_the_tools_the_agent_uses(session):
    listed = {tool["name"] for tool in session.request("tools/list")["tools"]}
    assert listed == {schema["name"] for schema in agent.ALL_TOOL_SCHEMAS}


def test_tool_call_over_mcp_reads_the_real_database(session):
    result = session.request("tools/call", {"name": "list_awards", "arguments": {}})
    assert "Nice meal" in json.dumps(result)


def test_tool_call_over_mcp_writes_to_the_real_database(session):
    session.request("tools/call", {"name": "add_points", "arguments": {"reason": "via MCP", "points": 12}})
    result = session.request("tools/call", {"name": "get_points_total", "arguments": {}})
    assert "12" in json.dumps(result)
