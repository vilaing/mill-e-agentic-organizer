"""Trust boundaries: what each visitor can reach, enforced in code rather than prompts."""
import base64
import hashlib
import json
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from conftest import FakeClaude, model_reply, text_block
from src import agent, demo, google_oauth
from src.tools import calendar_tool, gmail_tool
from src.web.main import app

GOOGLE_TOOLS = {**calendar_tool.DISPATCH, **gmail_tool.DISPATCH}
SCHEMA_NAMES = {schema["name"] for schema in agent.ALL_TOOL_SCHEMAS}


# --- Dispatch tables ---

@pytest.mark.parametrize("table", [agent._LOCAL_DISPATCH, agent._SANDBOX_DISPATCH, agent._SIGNED_IN_DISPATCH],
                         ids=["local", "anonymous", "signed-in"])
def test_model_sees_the_same_tool_names_in_every_mode(table):
    assert set(table) == SCHEMA_NAMES


def test_anonymous_visitors_cannot_reach_any_real_google_function():
    for name, real_function in GOOGLE_TOOLS.items():
        assert agent._SANDBOX_DISPATCH[name] is demo.DISPATCH[name]
        assert agent._SANDBOX_DISPATCH[name] is not real_function


def test_real_send_is_absent_from_every_hosted_table():
    for table in (agent._SANDBOX_DISPATCH, agent._SIGNED_IN_DISPATCH):
        assert gmail_tool.send_email not in table.values()


def test_signed_in_send_email_only_creates_a_draft(monkeypatch):
    """Even a direct request for send_email cannot deliver mail for a signed-in user."""
    service = MagicMock()
    service.users.return_value.drafts.return_value.create.return_value.execute.return_value = {"id": "d1"}
    monkeypatch.setattr(gmail_tool, "get_gmail_service", lambda: service)
    monkeypatch.setattr(demo, "google_email", lambda: "student@example.test")

    result = json.loads(agent.run_tool("send_email", {"to": "x@example.test", "subject": "s", "body": "b"}))

    assert result["status"] == "draft saved, not sent"
    service.users.return_value.drafts.return_value.create.assert_called_once()
    service.users.return_value.messages.return_value.send.assert_not_called()


def test_anonymous_send_email_never_touches_gmail(monkeypatch):
    def fail():
        raise AssertionError("Gmail should be unreachable")

    monkeypatch.setattr(gmail_tool, "get_gmail_service", fail)
    result = json.loads(agent.run_tool("send_email", {"to": "x@example.test", "subject": "s", "body": "b"}))
    assert result["status"].startswith("simulated")


# --- Visitor isolation ---

def _titles(client):
    return {assignment["title"] for assignment in client.get("/api/assignments").json()}


def test_visitors_cannot_see_each_others_data():
    alice, bob = TestClient(app), TestClient(app)
    alice.get("/api/points")
    bob.get("/api/points")
    assert alice.cookies[demo.COOKIE_NAME] != bob.cookies[demo.COOKIE_NAME]

    alice.post("/api/assignments", json={"title": "Only Alice has this"})
    assert "Only Alice has this" in _titles(alice)
    assert "Only Alice has this" not in _titles(bob)


@pytest.mark.parametrize("forged", ["../outside", "a" * 31, "g" * 32, "A" * 32])
def test_forged_session_cookies_are_never_used_as_a_file_path(forged):
    """The target file exists, so only the cookie's format check can reject it."""
    target = demo._sandbox_path(forged).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch()
    try:
        response = TestClient(app).get("/api/points", headers={"cookie": f"{demo.COOKIE_NAME}={forged}"})
    finally:
        target.unlink()
    issued = response.cookies[demo.COOKIE_NAME]
    assert response.status_code == 200
    assert issued != forged and demo._is_valid_visitor(issued)


def test_session_cookie_is_hidden_from_javascript():
    cookie = TestClient(app).get("/api/points").headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


# --- Spending limits ---

def _scripted_chat(monkeypatch):
    model = FakeClaude(model_reply("end_turn", text_block("ok")))
    monkeypatch.setattr(agent, "client", model)
    return model


def _chat(client):
    return client.post("/api/chat", json={"message": "hi"})


def test_per_visitor_cap_blocks_the_model_call(monkeypatch):
    monkeypatch.setattr(demo, "DEMO_MESSAGES_PER_VISITOR", 2)
    model = _scripted_chat(monkeypatch)
    client = TestClient(app)
    assert [_chat(client).status_code for _ in range(3)] == [200, 200, 429]
    assert len(model.requests) == 2


def test_global_cap_stops_new_visitors_too(monkeypatch):
    monkeypatch.setattr(demo, "DEMO_MESSAGES_PER_DAY", 1)
    model = _scripted_chat(monkeypatch)
    assert _chat(TestClient(app)).status_code == 200
    assert _chat(TestClient(app)).status_code == 429
    assert len(model.requests) == 1


def test_oversized_messages_are_rejected_before_the_model(monkeypatch):
    model = _scripted_chat(monkeypatch)
    assert TestClient(app).post("/api/chat", json={"message": "x" * 2001}).status_code == 422
    assert model.requests == []


# --- Google sign-in ---

def _start_sign_in(visitor="visitor-1"):
    return parse_qs(urlparse(google_oauth.authorization_url(visitor)).query)


def test_sign_in_uses_pkce_with_sha256():
    query = _start_sign_in()
    verifier = google_oauth._pending[query["state"][0]][1]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [expected]
    assert query["code_challenge_method"] == ["S256"]


def test_sign_in_cannot_be_finished_from_another_browser_session():
    state = _start_sign_in("visitor-1")["state"][0]
    with pytest.raises(google_oauth.SignInError):
        google_oauth.complete_sign_in(state, "code", "attacker")


def test_sign_in_state_works_only_once():
    state = _start_sign_in("visitor-1")["state"][0]
    with pytest.raises(google_oauth.SignInError):
        google_oauth.complete_sign_in(state, "code", "attacker")
    with pytest.raises(google_oauth.SignInError):
        google_oauth.complete_sign_in(state, "code", "visitor-1")


def test_unticked_google_permission_rejects_and_revokes_the_token(monkeypatch):
    calls = []

    def fake_post(url, **_):
        calls.append(url)
        response = MagicMock()
        response.json.return_value = {
            "access_token": "tok",
            "refresh_token": "refresh",
            "scope": "openid email https://www.googleapis.com/auth/gmail.readonly",
        }
        return response

    monkeypatch.setattr(google_oauth.httpx, "post", fake_post)
    state = _start_sign_in("visitor-1")["state"][0]
    with pytest.raises(google_oauth.SignInError) as error:
        google_oauth.complete_sign_in(state, "code", "visitor-1")
    assert error.value.reason == "permissions"
    assert calls == [google_oauth.TOKEN_URL, google_oauth.REVOKE_URL]
