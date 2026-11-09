"""Free-text rules: the model reads them once, then code enforces the result."""
import json

import pytest
from fastapi.testclient import TestClient

from conftest import FakeClaude, model_reply, text_block
from src import point_rules
from src.tools import db_tool
from src.web.main import app

RULE = "only give points on completion, not milestones/starting"
COMPLETION_ONLY = {
    "points_affected": True,
    "points_on_start": False,
    "points_on_milestones": False,
    "points_on_completion": True,
    "summary": "Points are earned when you finish.",
}


def interpreter(monkeypatch, *outcomes):
    model = FakeClaude(*outcomes)
    monkeypatch.setattr(point_rules, "client", model)
    return model


def answer(data, stop_reason="end_turn"):
    return model_reply(stop_reason, text_block(json.dumps(data)))


def test_completion_only_rule_is_enforced_by_code(db, monkeypatch):
    interpreter(monkeypatch, answer(COMPLETION_ONLY))
    point_rules.save_additional_rules(RULE)

    milestones = [{"title": "One", "point_percent": None}, {"title": "Two", "point_percent": None}]
    assignment = db_tool.add_assignment_with_milestones("Essay", "", "", 3, 3, milestones)["id"]
    assert db_tool.start_assignment(assignment)["points_awarded"] == 0
    for milestone in db_tool.list_milestones(assignment):
        assert db_tool.toggle_milestone(milestone["id"])["points_awarded"] == 0
    assert db_tool.complete_assignment(assignment)["points_awarded"] == 18


def test_model_output_is_constrained_by_a_json_schema(db, monkeypatch):
    model = interpreter(monkeypatch, answer(COMPLETION_ONLY))
    point_rules.save_additional_rules(RULE)
    request = model.requests[0]
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert f"<rules>\n{RULE}\n</rules>" == request["messages"][0]["content"]


def _nothing_was_saved():
    preferences = db_tool.get_preferences()
    return preferences["additional_rules"] == "" and preferences["points_on_start"] is True


def test_api_failure_fails_closed(db, monkeypatch):
    interpreter(monkeypatch, RuntimeError("API down"))
    with pytest.raises(RuntimeError):
        point_rules.save_additional_rules(RULE)
    assert _nothing_was_saved()


def test_refusal_is_not_treated_as_a_result(db, monkeypatch):
    interpreter(monkeypatch, answer(COMPLETION_ONLY, stop_reason="refusal"))
    with pytest.raises(point_rules.RuleInterpretationError):
        point_rules.save_additional_rules(RULE)
    assert _nothing_was_saved()


def test_truncated_output_is_not_treated_as_a_result(db, monkeypatch):
    interpreter(monkeypatch, answer(COMPLETION_ONLY, stop_reason="max_tokens"))
    with pytest.raises(point_rules.RuleInterpretationError):
        point_rules.save_additional_rules(RULE)
    assert _nothing_was_saved()


def test_a_rule_cannot_make_assignments_worth_nothing(db, monkeypatch):
    interpreter(monkeypatch, answer({**COMPLETION_ONLY, "points_on_completion": False}))
    point_rules.save_additional_rules("never give points")
    preferences = db_tool.get_preferences()
    assert preferences["points_on_start"] and preferences["points_on_milestones"] and preferences["points_on_completion"]


def test_unchanged_rules_cost_no_model_call(db, monkeypatch):
    model = interpreter(monkeypatch, answer(COMPLETION_ONLY))
    point_rules.save_additional_rules(RULE)
    point_rules.save_additional_rules(RULE)
    assert len(model.requests) == 1


def test_clearing_rules_restores_defaults_without_a_model_call(db, monkeypatch):
    model = interpreter(monkeypatch, answer(COMPLETION_ONLY))
    point_rules.save_additional_rules(RULE)
    point_rules.save_additional_rules("")
    assert len(model.requests) == 1
    assert _nothing_was_saved()


def test_settings_page_reports_503_when_the_model_is_down(monkeypatch):
    interpreter(monkeypatch, RuntimeError("API down"))
    client = TestClient(app)
    response = client.post("/api/preferences/additional-rules", json={"additional_rules": RULE})
    assert response.status_code == 503
    assert client.get("/api/preferences").json()["additional_rules"] == ""
