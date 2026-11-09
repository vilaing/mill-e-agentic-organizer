"""Shared fixtures. The suite is offline: no model calls, no Google calls.

The settings below must exist before anything imports src.config, and they take
priority over a developer's .env, so a real API key is never used here.
"""
import os
import tempfile
from types import SimpleNamespace

_TEMP_DIR = tempfile.mkdtemp(prefix="mill-e-tests-")
os.environ.update(
    ANTHROPIC_API_KEY="test-key-not-real",
    DEMO_MODE="true",
    DEMO_SANDBOX_DIR=os.path.join(_TEMP_DIR, "sandboxes"),
    DB_PATH=os.path.join(_TEMP_DIR, "unused.db"),
    GOOGLE_OAUTH_CLIENT_ID="test-client",
    GOOGLE_OAUTH_CLIENT_SECRET="test-secret",
    GOOGLE_OAUTH_REDIRECT_URI="https://example.test/callback",
)

import pytest  # noqa: E402

from src import agent, demo, google_oauth, point_rules  # noqa: E402
from src.db.db import init_db, reset_db, use_db  # noqa: E402


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_call(name, tool_input=None, call_id="call_1"):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=tool_input or {})


def model_reply(stop_reason, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


class FakeClaude:
    """Plays back scripted replies, repeating the last one, and records each request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = self

    def create(self, **request):
        self.requests.append({**request, "messages": list(request.get("messages", []))})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


class _NoModelCalls:
    @property
    def messages(self):
        raise AssertionError("This test tried to call the real model.")


def _no_google_calls(*_args, **_kwargs):
    raise AssertionError("This test tried to contact Google.")


@pytest.fixture(autouse=True)
def isolate_from_outside_world(monkeypatch):
    """Block model calls by default and give each test fresh usage counters."""
    monkeypatch.setattr(agent, "client", _NoModelCalls())
    monkeypatch.setattr(point_rules, "client", _NoModelCalls())
    monkeypatch.setattr(google_oauth.httpx, "post", _no_google_calls)
    monkeypatch.setattr(demo, "_total_today", 0)
    demo._visitor_counts.clear()


@pytest.fixture
def db(tmp_path):
    """A fresh database that every tool function in this test will use."""
    path = tmp_path / "test.db"
    token = use_db(str(path))
    init_db()
    yield path
    reset_db(token)
