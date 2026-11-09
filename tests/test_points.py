"""The points engine: the model never chooses these numbers, so they must be exact."""
from fractions import Fraction
from itertools import product

import pytest

from src.tools import db_tool

MOMENTS = [m for m in product([True, False], repeat=3) if any(m)]
CUSTOM_PERCENTS = [[10], [1, 99], [33, 33, 34], [25, None], [None, 7, None], [15, 15, 15, 15]]


def configure(style, moments=(True, True, True)):
    db_tool.set_reward_style(style)
    db_tool.set_point_rules(*moments, summary="")


def assignment_with_milestones(importance=3, difficulty=3, count=2):
    milestones = [{"title": f"Part {i}", "point_percent": None} for i in range(count)]
    return db_tool.add_assignment_with_milestones("Essay", "", "", importance, difficulty, milestones)["id"]


@pytest.mark.parametrize("style,moments", list(product(db_tool.REWARD_STYLES, MOMENTS)))
def test_parts_always_add_up_to_the_total(db, style, moments):
    """Every score, milestone count, reward style and rule combination."""
    configure(style, moments)
    milestone_lists = [[None] * count for count in range(7)] + CUSTOM_PERCENTS
    for importance, difficulty, percents in product(range(1, 6), range(1, 6), milestone_lists):
        split = db_tool._points_breakdown(importance, difficulty, percents)
        parts = [split["start_points"], split["completion_points"], *split["milestone_points"]]
        assert sum(parts) == importance * difficulty * db_tool.POINTS_MULTIPLIER
        assert len(split["milestone_points"]) == len(percents)
        assert min(parts) >= 0


def test_regression_18_point_assignment_no_longer_pays_16(db):
    """Four shares of 4.5 used to round to 4 each, losing 2 points."""
    configure("balanced")
    split = db_tool._points_breakdown(3, 3, [None, None])
    assert split == {"total": 18, "start_points": 5, "completion_points": 5, "milestone_points": [4, 4]}


@pytest.mark.parametrize("amounts", [
    [Fraction(9, 2)] * 4,
    [Fraction(10, 3)] * 3,
    [Fraction(1, 7)] * 7,
    [Fraction(50, 3), Fraction(50, 3), Fraction(50, 3)],
    [Fraction(5), Fraction(0), Fraction(1, 2), Fraction(1, 2)],
])
def test_rounding_keeps_the_sum_and_stays_within_one_point(amounts):
    rounded = db_tool._whole_numbers_summing_to_total(amounts)
    assert sum(rounded) == sum(amounts)
    assert all(abs(whole - exact) < 1 for whole, exact in zip(rounded, amounts))


@pytest.mark.parametrize("style", db_tool.REWARD_STYLES)
def test_fully_worked_assignment_pays_its_exact_total_in_the_ledger(db, style):
    configure(style)
    for importance, difficulty, count in product(range(1, 6), range(1, 6), range(5)):
        before = db_tool.get_points_total()["total_points"]
        assignment = assignment_with_milestones(importance, difficulty, count)
        db_tool.start_assignment(assignment)
        for milestone in db_tool.list_milestones(assignment):
            db_tool.toggle_milestone(milestone["id"])
        db_tool.complete_assignment(assignment)

        expected = importance * difficulty * db_tool.POINTS_MULTIPLIER
        assert db_tool.get_points_total()["total_points"] - before == expected
        assert db_tool.get_assignment(assignment)["points_earned"] == expected


def test_float_percentages_cannot_tip_a_rounding_boundary(db):
    """50/6 is inexact as a float; exact fractions give a stable split."""
    configure("balanced")
    split = db_tool._points_breakdown(5, 5, [None] * 6)
    assert sum(split["milestone_points"]) + split["start_points"] + split["completion_points"] == 50


def test_milestone_cannot_be_completed_before_the_assignment_starts(db):
    assignment = assignment_with_milestones()
    milestone = db_tool.list_milestones(assignment)[0]
    assert "Start this assignment" in db_tool.toggle_milestone(milestone["id"])["error"]
    assert db_tool.get_points_total()["total_points"] == 0


def test_unchecking_a_milestone_reverses_exactly_what_it_paid(db):
    assignment = assignment_with_milestones()
    db_tool.start_assignment(assignment)
    after_start = db_tool.get_points_total()["total_points"]
    milestone = db_tool.list_milestones(assignment)[0]

    assert db_tool.toggle_milestone(milestone["id"])["points_awarded"] == 4
    db_tool.toggle_milestone(milestone["id"])
    assert db_tool.get_points_total()["total_points"] == after_start


def test_repeating_start_or_complete_never_pays_twice(db):
    assignment = assignment_with_milestones(count=0)
    db_tool.start_assignment(assignment)
    db_tool.start_assignment(assignment)
    db_tool.complete_assignment(assignment)
    db_tool.complete_assignment(assignment)
    assert db_tool.get_points_total()["total_points"] == 18


def _award(name):
    return next(a for a in db_tool.list_awards() if a["name"] == name)


def test_redeeming_without_enough_points_changes_nothing(db):
    db_tool.add_points("seed", 10)
    result = db_tool.redeem_award(_award("Nice meal")["id"])
    assert result["need"] == 60 and result["have"] == 10
    assert db_tool.get_points_total()["total_points"] == 10


def test_redeeming_a_quantity_charges_for_every_unit(db):
    db_tool.add_points("seed", 10)
    result = db_tool.redeem_award(_award("$1 towards a for-fun purchase")["id"], quantity=3)
    assert result["points_spent"] == 9 and result["remaining_points"] == 1
    assert db_tool.get_reward_banks()["dollars"] == 3


@pytest.mark.parametrize("quantity", [0, -1, db_tool.MAX_REDEEM_QUANTITY + 1])
def test_invalid_quantities_are_rejected(db, quantity):
    db_tool.add_points("seed", 1000)
    assert "error" in db_tool.redeem_award(_award("Nice meal")["id"], quantity=quantity)
    assert db_tool.get_points_total()["total_points"] == 1000
