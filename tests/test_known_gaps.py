"""Known limitations, written as tests of the behavior the app should have.

Each one is expected to fail today. strict=True makes the suite report when a
gap gets fixed, so this list can't quietly go out of date.
"""
import pytest

from src.tools import db_tool


@pytest.mark.xfail(strict=True, reason="The 2-50 limit on add_points is only a suggestion in the tool description.")
def test_add_points_rejects_amounts_outside_the_allowed_range(db):
    assert "error" in db_tool.add_points("I asked nicely", 1_000_000)
    assert db_tool.get_points_total()["total_points"] == 0


@pytest.mark.xfail(strict=True, reason="Status and ledger are separate commits, so a crash between them loses points.")
def test_starting_an_assignment_is_atomic_with_its_ledger_entry(db, monkeypatch):
    assignment = db_tool.add_assignment("Essay", "", "", 3, 3)["id"]

    def crash(**_):
        raise RuntimeError("process died here")

    monkeypatch.setattr(db_tool, "add_points", crash)
    with pytest.raises(RuntimeError):
        db_tool.start_assignment(assignment)
    assert db_tool.get_assignment(assignment)["status"] == "open"
