"""Assignment tracker, recruiting pipeline, points, and awards.

Each public function here is a "tool" the agent can call. TOOL_SCHEMAS is
what gets sent to the Claude API so it knows these tools exist.

Points for assignments are DETERMINISTIC, not left to the model's judgment:
total = importance * difficulty * POINTS_MULTIPLIER, split between starting
and finishing the task according to the user's reward_style preference. If
the assignment has milestones, they carve out MILESTONE_POOL_FRACTION of
that total (split evenly across them) and start/completion split the rest;
with no milestones, start/completion still split 100%, unchanged. A milestone
can instead set point_percent, a custom share of the assignment's total, with
start/completion splitting whatever remains. See _points_breakdown(). This
keeps the reward system consistent across runs.
add_points() is still freeform/judgment-based for things that don't fit the
assignment lifecycle (e.g. recruiting progress) -- that's an intentional,
separate tradeoff.
"""
from fractions import Fraction
from math import floor

from src.db.db import get_conn

POINTS_MULTIPLIER = 2  # importance(1-5) * difficulty(1-5) * this = 2-50 pts per task

# reward_style -> fraction of a task's points awarded at START (vs completion)
REWARD_STYLES = {
    "mostly_encouragement": 0.8,  # reward starting; good for task-initiation struggles
    "balanced": 0.5,
    "mostly_completion": 0.2,     # reward finishing; good for completion-driven gratification
}

# When an assignment has milestones, this fraction of its total points is
# reserved for them (split evenly across however many exist); the rest still
# splits between start/completion per reward_style, same as an assignment
# with no milestones at all (which keeps 100% of its points in that split).
MILESTONE_POOL_FRACTION = 0.5

MAX_REDEEM_QUANTITY = 99


# --- Preferences ---

def get_reward_style() -> dict:
    conn = get_conn()
    row = conn.execute("SELECT reward_style FROM preferences WHERE id = 1").fetchone()
    conn.close()
    style = row["reward_style"] if row else "balanced"
    return {"reward_style": style, "start_weight": REWARD_STYLES[style]}


def set_reward_style(reward_style: str) -> dict:
    if reward_style not in REWARD_STYLES:
        return {"error": f"Invalid reward_style. Choose one of: {list(REWARD_STYLES.keys())}"}
    conn = get_conn()
    conn.execute(
        "UPDATE preferences SET reward_style = ?, updated_at = datetime('now') WHERE id = 1",
        (reward_style,),
    )
    conn.commit()
    conn.close()
    return {"reward_style": reward_style, "start_weight": REWARD_STYLES[reward_style]}


def get_preferences() -> dict:
    """Full preferences snapshot, including whether first-time setup has run yet."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM preferences WHERE id = 1").fetchone()
    conn.close()
    if row is None:
        return {
            "reward_style": "balanced",
            "start_weight": REWARD_STYLES["balanced"],
            "additional_rules": "",
            "morning_reminders": True,
            "onboarding_completed": False,
            "points_on_start": True,
            "points_on_milestones": True,
            "points_on_completion": True,
            "point_rules_summary": "",
        }
    return {
        "reward_style": row["reward_style"],
        "start_weight": REWARD_STYLES[row["reward_style"]],
        "additional_rules": row["additional_rules"] or "",
        "morning_reminders": bool(row["morning_reminders"]),
        "onboarding_completed": bool(row["onboarding_completed"]),
        "points_on_start": bool(row["points_on_start"]),
        "points_on_milestones": bool(row["points_on_milestones"]),
        "points_on_completion": bool(row["points_on_completion"]),
        "point_rules_summary": row["point_rules_summary"] or "",
    }


def set_point_rules(points_on_start: bool, points_on_milestones: bool, points_on_completion: bool, summary: str) -> None:
    """Store which moments earn points. Written by src/point_rules.py, not a chat tool."""
    conn = get_conn()
    conn.execute(
        """UPDATE preferences SET points_on_start = ?, points_on_milestones = ?, points_on_completion = ?,
           point_rules_summary = ?, updated_at = datetime('now') WHERE id = 1""",
        (int(points_on_start), int(points_on_milestones), int(points_on_completion), summary),
    )
    conn.commit()
    conn.close()


def complete_setup(reward_style: str, additional_rules: str = "", morning_reminders: bool = True) -> dict:
    """Save the user's answers from first-time setup and mark onboarding done."""
    if reward_style not in REWARD_STYLES:
        return {"error": f"Invalid reward_style. Choose one of: {list(REWARD_STYLES.keys())}"}
    conn = get_conn()
    conn.execute(
        """UPDATE preferences SET reward_style = ?, additional_rules = ?,
           morning_reminders = ?, onboarding_completed = 1, updated_at = datetime('now')
           WHERE id = 1""",
        (reward_style, additional_rules, int(morning_reminders)),
    )
    conn.commit()
    conn.close()
    return {
        "reward_style": reward_style,
        "start_weight": REWARD_STYLES[reward_style],
        "additional_rules": additional_rules,
        "morning_reminders": morning_reminders,
        "onboarding_completed": True,
    }


def set_additional_rules(additional_rules: str) -> dict:
    conn = get_conn()
    conn.execute(
        "UPDATE preferences SET additional_rules = ?, updated_at = datetime('now') WHERE id = 1",
        (additional_rules,),
    )
    conn.commit()
    conn.close()
    return {"additional_rules": additional_rules}


def set_morning_reminders(enabled: bool) -> dict:
    conn = get_conn()
    conn.execute(
        "UPDATE preferences SET morning_reminders = ?, updated_at = datetime('now') WHERE id = 1",
        (int(enabled),),
    )
    conn.commit()
    conn.close()
    return {"morning_reminders": enabled}


def _start_weight() -> float:
    conn = get_conn()
    row = conn.execute("SELECT reward_style FROM preferences WHERE id = 1").fetchone()
    conn.close()
    style = row["reward_style"] if row else "balanced"
    return REWARD_STYLES[style]


def _milestone_percents(conn, assignment_id: int) -> list[int | None]:
    """Each milestone's custom percent (None = default), oldest first."""
    rows = conn.execute(
        "SELECT point_percent FROM milestones WHERE assignment_id = ? ORDER BY id", (assignment_id,)
    ).fetchall()
    return [row["point_percent"] for row in rows]


def _default_milestone_percent(milestone_count: int) -> Fraction:
    """An even slice of the default pool. Exact fractions keep point rounding
    stable; floats like 50/6 can tip a value across a rounding boundary."""
    return Fraction(MILESTONE_POOL_FRACTION) * 100 / max(milestone_count, 1)


def _milestone_total_percent(percents: list[int | None]) -> Fraction:
    """Share of an assignment's points its milestones use, before any scaling."""
    default_percent = _default_milestone_percent(len(percents))
    return sum((default_percent if percent is None else Fraction(percent) for percent in percents), Fraction(0))


def _milestone_percent_error(percents: list[int | None]) -> str | None:
    total = _milestone_total_percent(percents)
    if total > 100:
        return f"Milestones would use {round(total)}% of this assignment's points. Keep the total at 100% or less."
    return None


def _whole_numbers_summing_to_total(amounts: list[Fraction]) -> list[int]:
    """Round down, then hand the leftover points to the largest fractions.
    Rounding each part on its own can lose points (four shares of 4.5 from 18
    round to 16). Ties go to the earliest entry."""
    rounded = [floor(amount) for amount in amounts]
    leftover = int(sum(amounts)) - sum(rounded)
    largest_first = sorted(range(len(amounts)), key=lambda i: (rounded[i] - amounts[i], i))
    for index in largest_first[:leftover]:
        rounded[index] += 1
    return rounded


def _points_breakdown(importance: int, difficulty: int, milestone_percents: list[int | None]) -> dict:
    """Split an assignment's total points into start / completion / per-milestone
    shares that always add up to the total. With no milestones, start+completion
    split 100%; with milestones, they split what's left after the milestones'
    shares. A moment the user's rules turned off passes its points to the others."""
    total = importance * difficulty * POINTS_MULTIPLIER
    prefs = get_preferences()
    on_start, on_completion = prefs["points_on_start"], prefs["points_on_completion"]
    active_percents = milestone_percents if prefs["points_on_milestones"] else []

    used_percent = _milestone_total_percent(active_percents)
    only_milestones = bool(active_percents) and not on_start and not on_completion
    # Scale up if milestones are the only moment left. Scale down if deleting a
    # milestone pushed the rest over 100%.
    scale = 100 / used_percent if only_milestones or used_percent > 100 else Fraction(1)
    default_percent = _default_milestone_percent(len(active_percents))
    milestone_amounts = [
        total * (default_percent if percent is None else percent) * scale / 100
        for percent in active_percents
    ] or [Fraction(0)] * len(milestone_percents)

    pool = total - sum(milestone_amounts, Fraction(0))
    if on_start and on_completion:
        start_amount = pool * Fraction(str(_start_weight()))
    else:
        start_amount = pool if on_start else Fraction(0)
    completion_amount = pool - start_amount

    completion_points, start_points, *milestone_points = _whole_numbers_summing_to_total(
        [completion_amount, start_amount, *milestone_amounts]
    )
    return {
        "total": total,
        "start_points": start_points,
        "completion_points": completion_points,
        "milestone_points": milestone_points,
    }


# --- Assignments ---

def add_assignment(title: str, course: str = "", due_date: str = "",
                    importance: int = 3, difficulty: int = 3) -> dict:
    importance = max(1, min(5, importance))
    difficulty = max(1, min(5, difficulty))
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO assignments (title, course, due_date, importance, difficulty) VALUES (?, ?, ?, ?, ?)",
        (title, course, due_date, importance, difficulty),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    total = importance * difficulty * POINTS_MULTIPLIER
    return {"id": row_id, "title": title, "status": "added", "total_points_available": total}


def add_assignment_with_milestones(title: str, course: str, due_date: str, importance: int,
                                   difficulty: int, milestones: list[dict]) -> dict:
    """Create an assignment and its milestones, checking the full set of
    percentages first so a bad total can't leave a half-created assignment."""
    error = _milestone_percent_error([m["point_percent"] for m in milestones])
    if error:
        return {"error": error}
    created = add_assignment(title, course, due_date, importance, difficulty)
    conn = get_conn()
    conn.executemany(
        "INSERT INTO milestones (assignment_id, title, point_percent) VALUES (?, ?, ?)",
        [(created["id"], m["title"], m["point_percent"]) for m in milestones],
    )
    conn.commit()
    conn.close()
    return created


_ASSIGNMENTS_WITH_MILESTONES = """
    SELECT a.*,
        (SELECT COUNT(*) FROM milestones m WHERE m.assignment_id = a.id) AS milestone_count,
        (SELECT COUNT(*) FROM milestones m WHERE m.assignment_id = a.id AND m.done = 1) AS milestones_done
    FROM assignments a
"""


def list_assignments(status: str = "open") -> list[dict]:
    conn = get_conn()
    if status == "all":
        rows = conn.execute(f"{_ASSIGNMENTS_WITH_MILESTONES} ORDER BY due_date").fetchall()
    elif status == "active":
        rows = conn.execute(
            f"{_ASSIGNMENTS_WITH_MILESTONES} WHERE a.status IN ('open', 'in_progress') ORDER BY due_date"
        ).fetchall()
    else:
        rows = conn.execute(
            f"{_ASSIGNMENTS_WITH_MILESTONES} WHERE a.status = ? ORDER BY due_date", (status,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_assignment(assignment_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(f"{_ASSIGNMENTS_WITH_MILESTONES} WHERE a.id = ?", (assignment_id,)).fetchone()
    conn.close()
    if row is None:
        return {"error": f"No assignment with id {assignment_id}"}
    return dict(row)


def delete_assignment(assignment_id: int) -> dict:
    """Remove an assignment (and its milestones) entirely. Does not award or
    claw back any points -- deleting is just removal, not completion."""
    conn = get_conn()
    row = conn.execute("SELECT id FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    if row is None:
        conn.close()
        return {"error": f"No assignment with id {assignment_id}"}
    conn.execute("DELETE FROM milestones WHERE assignment_id = ?", (assignment_id,))
    conn.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
    conn.commit()
    conn.close()
    return {"id": assignment_id, "status": "deleted"}


def start_assignment(assignment_id: int) -> dict:
    """Mark a task as started and award the 'starting' portion of its points."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    if row is None:
        conn.close()
        return {"error": f"No assignment with id {assignment_id}"}
    if row["status"] != "open":
        conn.close()
        return {"id": assignment_id, "status": row["status"], "note": "Already started or done; no points awarded."}

    breakdown = _points_breakdown(row["importance"], row["difficulty"], _milestone_percents(conn, assignment_id))
    start_points = breakdown["start_points"]

    conn.execute("UPDATE assignments SET status = 'in_progress', points_earned = points_earned + ? WHERE id = ?",
                 (start_points, assignment_id))
    conn.commit()
    conn.close()

    result = add_points(reason=f"Started '{row['title']}'", points=start_points) if start_points > 0 else {"total_points": get_points_total()["total_points"]}
    return {"id": assignment_id, "status": "in_progress", "points_awarded": start_points, "total_points": result["total_points"]}


def complete_assignment(assignment_id: int) -> dict:
    """Mark a task done and award the 'completion' portion of its points."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    if row is None:
        conn.close()
        return {"error": f"No assignment with id {assignment_id}"}
    if row["status"] == "done":
        conn.close()
        return {"id": assignment_id, "status": "done", "note": "Already completed; no additional points."}

    breakdown = _points_breakdown(row["importance"], row["difficulty"], _milestone_percents(conn, assignment_id))
    completion_points = breakdown["completion_points"]

    conn.execute("UPDATE assignments SET status = 'done', points_earned = points_earned + ? WHERE id = ?",
                 (completion_points, assignment_id))
    conn.commit()
    conn.close()

    result = add_points(reason=f"Completed '{row['title']}'", points=completion_points) if completion_points > 0 else {"total_points": get_points_total()["total_points"]}
    return {"id": assignment_id, "status": "done", "points_awarded": completion_points, "total_points": result["total_points"]}


# --- Milestones ---

def add_milestone(assignment_id: int, title: str, point_percent: int | None = None) -> dict:
    if point_percent is not None and not 1 <= point_percent <= 100:
        return {"error": "point_percent must be a whole number from 1 to 100."}
    conn = get_conn()
    assignment = conn.execute("SELECT id FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    if assignment is None:
        conn.close()
        return {"error": f"No assignment with id {assignment_id}"}
    error = _milestone_percent_error([*_milestone_percents(conn, assignment_id), point_percent])
    if error:
        conn.close()
        return {"error": error}
    cur = conn.execute(
        "INSERT INTO milestones (assignment_id, title, point_percent) VALUES (?, ?, ?)",
        (assignment_id, title, point_percent),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return {"id": row_id, "assignment_id": assignment_id, "title": title, "point_percent": point_percent, "done": False}


def list_milestones(assignment_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM milestones WHERE assignment_id = ? ORDER BY id", (assignment_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_milestone(milestone_id: int) -> dict:
    conn = get_conn()
    conn.execute("DELETE FROM milestones WHERE id = ?", (milestone_id,))
    conn.commit()
    conn.close()
    return {"id": milestone_id, "status": "deleted"}


def toggle_milestone(milestone_id: int) -> dict:
    """Check or uncheck a milestone, awarding/reversing its share of the
    assignment's points. The per-milestone amount is fixed at the moment a
    milestone is checked (based on the milestone count at that time) and
    stored on the row, so unchecking always reverses exactly what was given
    -- even if milestones were added or removed in between."""
    conn = get_conn()
    milestone = conn.execute("SELECT * FROM milestones WHERE id = ?", (milestone_id,)).fetchone()
    if milestone is None:
        conn.close()
        return {"error": f"No milestone with id {milestone_id}"}
    assignment = conn.execute(
        "SELECT * FROM assignments WHERE id = ?", (milestone["assignment_id"],)
    ).fetchone()

    if not milestone["done"]:
        if assignment["status"] == "open":
            conn.close()
            return {"error": "Start this assignment before completing its milestones."}
        sibling_ids =[row["id"] for row in conn.execute(
            "SELECT id FROM milestones WHERE assignment_id = ? ORDER BY id", (assignment["id"],)
        ).fetchall()]
        breakdown = _points_breakdown(
            assignment["importance"], assignment["difficulty"], _milestone_percents(conn, assignment["id"])
        )
        pts = breakdown["milestone_points"][sibling_ids.index(milestone_id)]
        conn.execute("UPDATE milestones SET done = 1, points_awarded = ? WHERE id = ?", (pts, milestone_id))
        conn.execute("UPDATE assignments SET points_earned = points_earned + ? WHERE id = ?", (pts, assignment["id"]))
        conn.commit()
        conn.close()
        if pts > 0:
            add_points(reason=f"Milestone: {milestone['title']} ({assignment['title']})", points=pts)
        return {"id": milestone_id, "done": True, "points_awarded": pts}
    else:
        pts = milestone["points_awarded"]
        conn.execute("UPDATE milestones SET done = 0, points_awarded = 0 WHERE id = ?", (milestone_id,))
        conn.execute("UPDATE assignments SET points_earned = MAX(0, points_earned - ?) WHERE id = ?", (pts, assignment["id"]))
        conn.commit()
        conn.close()
        if pts > 0:
            add_points(reason=f"Unchecked milestone: {milestone['title']} ({assignment['title']})", points=-pts)
        return {"id": milestone_id, "done": False, "points_awarded": 0}


# --- Recruiting ---

def upsert_recruiting(company: str, role: str = "", stage: str = "applied",
                       next_action: str = "", next_action_date: str = "",
                       notes: str = "") -> dict:
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM recruiting WHERE company = ? AND role = ?", (company, role)
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE recruiting SET stage=?, next_action=?, next_action_date=?,
               notes=?, updated_at=datetime('now') WHERE id=?""",
            (stage, next_action, next_action_date, notes, existing["id"]),
        )
        row_id = existing["id"]
    else:
        cur = conn.execute(
            """INSERT INTO recruiting (company, role, stage, next_action, next_action_date, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (company, role, stage, next_action, next_action_date, notes),
        )
        row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": row_id, "company": company, "stage": stage}


def list_recruiting() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM recruiting ORDER BY next_action_date").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Points ---

def add_points(reason: str, points: int) -> dict:
    conn = get_conn()
    conn.execute("INSERT INTO points_log (reason, points) VALUES (?, ?)", (reason, points))
    conn.commit()
    total = conn.execute("SELECT SUM(points) AS total FROM points_log").fetchone()["total"]
    conn.close()
    return {"reason": reason, "points_awarded": points, "total_points": total or 0}


def get_points_total() -> dict:
    conn = get_conn()
    total = conn.execute("SELECT SUM(points) AS total FROM points_log").fetchone()["total"]
    conn.close()
    return {"total_points": total or 0}


# --- Awards ---

def list_awards(active_only: bool = True) -> list[dict]:
    conn = get_conn()
    if active_only:
        rows = conn.execute("SELECT * FROM awards WHERE active = 1 ORDER BY cost").fetchall()
    else:
        rows = conn.execute("SELECT * FROM awards ORDER BY cost").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_award(name: str, cost: int, description: str = "", break_minutes: int = 0, dollar_value: float = 0) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO awards (name, description, cost, is_preset, break_minutes, dollar_value) VALUES (?, ?, ?, 0, ?, ?)",
            (name, description, cost, break_minutes, dollar_value),
        )
        conn.commit()
        row_id = cur.lastrowid
    except Exception as e:
        conn.close()
        return {"error": str(e)}
    conn.close()
    return {"id": row_id, "name": name, "cost": cost, "break_minutes": break_minutes, "dollar_value": dollar_value, "status": "added"}


def deactivate_award(award_id: int) -> dict:
    conn = get_conn()
    conn.execute("UPDATE awards SET active = 0 WHERE id = ?", (award_id,))
    conn.commit()
    conn.close()
    return {"id": award_id, "status": "deactivated"}


def redeem_award(award_id: int, quantity: int = 1) -> dict:
    if not 1 <= quantity <= MAX_REDEEM_QUANTITY:
        return {"error": f"Quantity must be from 1 to {MAX_REDEEM_QUANTITY}."}
    conn = get_conn()
    award = conn.execute("SELECT * FROM awards WHERE id = ? AND active = 1", (award_id,)).fetchone()
    if award is None:
        conn.close()
        return {"error": f"No active award with id {award_id}"}

    total = conn.execute("SELECT SUM(points) AS total FROM points_log").fetchone()["total"] or 0
    cost = award["cost"] * quantity
    if total < cost:
        conn.close()
        return {"error": f"Not enough points: this costs {cost} and you have {total}.", "have": total, "need": cost}

    label = f"{quantity} x {award['name']}" if quantity > 1 else award["name"]
    conn.execute("INSERT INTO points_log (reason, points) VALUES (?, ?)",
                 (f"Redeemed: {label}", -cost))
    conn.executemany("INSERT INTO redemptions (award_id, points_spent) VALUES (?, ?)",
                     [(award_id, award["cost"])] * quantity)
    break_minutes = (award["break_minutes"] or 0) * quantity
    dollar_value = (award["dollar_value"] or 0) * quantity
    if break_minutes or dollar_value:
        conn.execute(
            "UPDATE reward_banks SET break_minutes = break_minutes + ?, dollars = dollars + ?, updated_at = datetime('now') WHERE id = 1",
            (break_minutes, dollar_value),
        )
    if dollar_value:
        conn.execute(
            "INSERT INTO dollar_transactions (amount, reason) VALUES (?, ?)",
            (dollar_value, f"Redeemed: {label}"),
        )
    conn.commit()
    new_total = conn.execute("SELECT SUM(points) AS total FROM points_log").fetchone()["total"] or 0
    banks = conn.execute("SELECT break_minutes, dollars FROM reward_banks WHERE id = 1").fetchone()
    conn.close()
    return {
        "redeemed": award["name"],
        "quantity": quantity,
        "points_spent": cost,
        "remaining_points": new_total,
        "break_minutes_added": break_minutes,
        "dollar_value_added": dollar_value,
        "break_bank_total": banks["break_minutes"] if banks else break_minutes,
        "dollar_bank_total": banks["dollars"] if banks else dollar_value,
    }


# --- Reward banks (break time / $$ accumulated from redeeming awards) ---

def get_reward_banks() -> dict:
    conn = get_conn()
    row = conn.execute("SELECT break_minutes, dollars FROM reward_banks WHERE id = 1").fetchone()
    conn.close()
    if row is None:
        return {"break_minutes": 0, "dollars": 0.0}
    return {"break_minutes": row["break_minutes"], "dollars": row["dollars"]}


def spend_break_minutes(minutes: int) -> dict:
    if minutes <= 0:
        return {"error": "minutes must be positive"}
    conn = get_conn()
    row = conn.execute("SELECT break_minutes FROM reward_banks WHERE id = 1").fetchone()
    available = row["break_minutes"] if row else 0
    if minutes > available:
        conn.close()
        return {"error": "Not enough banked break time", "have": available, "need": minutes}
    conn.execute(
        "UPDATE reward_banks SET break_minutes = break_minutes - ?, updated_at = datetime('now') WHERE id = 1",
        (minutes,),
    )
    conn.commit()
    conn.close()
    return {"break_minutes": available - minutes, "spent": minutes}


def spend_dollars(amount: float, reason: str = "") -> dict:
    if amount <= 0:
        return {"error": "amount must be positive"}
    conn = get_conn()
    row = conn.execute("SELECT dollars FROM reward_banks WHERE id = 1").fetchone()
    available = row["dollars"] if row else 0.0
    if amount > available:
        conn.close()
        return {"error": "Not enough banked $$", "have": available, "need": amount}
    conn.execute(
        "UPDATE reward_banks SET dollars = dollars - ?, updated_at = datetime('now') WHERE id = 1",
        (amount,),
    )
    conn.execute(
        "INSERT INTO dollar_transactions (amount, reason) VALUES (?, ?)",
        (-amount, reason or "Purchase"),
    )
    conn.commit()
    conn.close()
    return {"dollars": available - amount, "spent": amount}


def list_dollar_transactions(limit: int = 10) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM dollar_transactions ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Tool schemas for the Claude API ---
TOOL_SCHEMAS = [
    {
        "name": "add_assignment",
        "description": "Add a new assignment/task to track. importance and difficulty (1-5 each) determine how many points it's worth.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "course": {"type": "string"},
                "due_date": {"type": "string"},
                "importance": {"type": "integer", "description": "1 (low) to 5 (high)"},
                "difficulty": {"type": "integer", "description": "1 (easy) to 5 (hard)"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_assignments",
        "description": "List assignments, filtered by status: 'open', 'in_progress', 'done', 'active' (open + in_progress), or 'all'.",
        "input_schema": {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["open", "in_progress", "active", "done", "all"]}},
        },
    },
    {
        "name": "get_assignment",
        "description": "Get a single assignment by id, including its milestone counts.",
        "input_schema": {
            "type": "object",
            "properties": {"assignment_id": {"type": "integer"}},
            "required": ["assignment_id"],
        },
    },
    {
        "name": "delete_assignment",
        "description": "Delete an assignment and its milestones entirely. Does not award or claw back any points -- use this to remove a task, not complete_assignment.",
        "input_schema": {
            "type": "object",
            "properties": {"assignment_id": {"type": "integer"}},
            "required": ["assignment_id"],
        },
    },
    {
        "name": "start_assignment",
        "description": "Mark an assignment as started (in progress). Awards the 'starting' portion of its points based on the user's reward style -- call this when the user says they're beginning a task, not just when they add it.",
        "input_schema": {
            "type": "object",
            "properties": {"assignment_id": {"type": "integer"}},
            "required": ["assignment_id"],
        },
    },
    {
        "name": "complete_assignment",
        "description": "Mark an assignment as done. Awards the 'completion' portion of its points based on the user's reward style.",
        "input_schema": {
            "type": "object",
            "properties": {"assignment_id": {"type": "integer"}},
            "required": ["assignment_id"],
        },
    },
    {
        "name": "add_milestone",
        "description": "Add a sub-task/milestone within an assignment (e.g. 'HTML page', 'stylesheet' for a website project). When an assignment has milestones, they carve out a share of its points split evenly across however many exist, unless point_percent is given.",
        "input_schema": {
            "type": "object",
            "properties": {
                "assignment_id": {"type": "integer"},
                "title": {"type": "string"},
                "point_percent": {"type": "integer", "description": "Optional custom share of the assignment's total points, 1-100. Only set this if the user asks for one."},
            },
            "required": ["assignment_id", "title"],
        },
    },
    {
        "name": "list_milestones",
        "description": "List the milestones for an assignment, including which are done.",
        "input_schema": {
            "type": "object",
            "properties": {"assignment_id": {"type": "integer"}},
            "required": ["assignment_id"],
        },
    },
    {
        "name": "toggle_milestone",
        "description": "Check or uncheck a milestone by its id -- checking awards its share of the assignment's points, unchecking reverses that same amount. Call this when the user says they've finished (or wants to undo) a specific milestone. A milestone can't be checked until its assignment has been started.",
        "input_schema": {
            "type": "object",
            "properties": {"milestone_id": {"type": "integer"}},
            "required": ["milestone_id"],
        },
    },
    {
        "name": "delete_milestone",
        "description": "Delete a milestone from an assignment. Points already awarded for it are not clawed back.",
        "input_schema": {
            "type": "object",
            "properties": {"milestone_id": {"type": "integer"}},
            "required": ["milestone_id"],
        },
    },
    {
        "name": "get_reward_style",
        "description": "Get the user's current reward style preference (how points are split between starting and finishing tasks).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_reward_style",
        "description": "Set the user's reward style. 'mostly_encouragement' rewards starting tasks more (for users who struggle to begin); 'mostly_completion' rewards finishing more (for completion-driven gratification); 'balanced' splits evenly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reward_style": {"type": "string", "enum": ["mostly_encouragement", "balanced", "mostly_completion"]},
            },
            "required": ["reward_style"],
        },
    },
    {
        "name": "get_preferences",
        "description": "Get the user's full preferences snapshot: reward_style, additional_rules, morning_reminders, and whether first-time setup (onboarding_completed) has been run yet. Check this before the first add_assignment call in a session to see if setup is needed.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "complete_setup",
        "description": "Save the user's answers from first-time setup (reward style, optional additional rules, morning reminders opt-in/out) and mark onboarding as completed. Call this once, after walking the user through setup, before adding their first assignment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reward_style": {"type": "string", "enum": ["mostly_encouragement", "balanced", "mostly_completion"]},
                "additional_rules": {"type": "string", "description": "Any custom instructions the user wants followed going forward. Empty string if none."},
                "morning_reminders": {"type": "boolean", "description": "Whether the user wants morning reminders."},
            },
            "required": ["reward_style"],
        },
    },
    {
        "name": "set_additional_rules",
        "description": "Update the user's custom additional rules/instructions after setup.",
        "input_schema": {
            "type": "object",
            "properties": {"additional_rules": {"type": "string"}},
            "required": ["additional_rules"],
        },
    },
    {
        "name": "set_morning_reminders",
        "description": "Opt the user in or out of morning reminders after setup.",
        "input_schema": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
        },
    },
    {
        "name": "upsert_recruiting",
        "description": "Add or update a recruiting pipeline entry for a company/role, including stage and next action.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "role": {"type": "string"},
                "stage": {"type": "string", "enum": ["applied", "oa", "interview", "offer", "rejected"]},
                "next_action": {"type": "string"},
                "next_action_date": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["company"],
        },
    },
    {
        "name": "list_recruiting",
        "description": "List all recruiting pipeline entries, sorted by next action date.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_points",
        "description": "Award points for something outside the assignment lifecycle (e.g. recruiting progress). Use your judgment for the amount, keeping it in a similar range to assignment points (roughly 2-50).",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "points": {"type": "integer"},
            },
            "required": ["reason", "points"],
        },
    },
    {
        "name": "get_points_total",
        "description": "Get the user's current total reward points.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_awards",
        "description": "List available awards the user can redeem points for.",
        "input_schema": {
            "type": "object",
            "properties": {"active_only": {"type": "boolean"}},
        },
    },
    {
        "name": "add_award",
        "description": "Create a new custom award the user can redeem points for later. Optionally mark it as a break-time or $$ award: redeeming it then banks break_minutes and/or dollar_value into the user's reward banks (see get_reward_banks) instead of (or in addition to) being a one-off reward.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "cost": {"type": "integer"},
                "description": {"type": "string"},
                "break_minutes": {"type": "integer", "description": "Minutes of break time banked when redeemed. 0 if not a break award."},
                "dollar_value": {"type": "number", "description": "Dollar amount banked when redeemed. 0 if not a $$ award."},
            },
            "required": ["name", "cost"],
        },
    },
    {
        "name": "deactivate_award",
        "description": "Deactivate an award so it no longer shows up as redeemable.",
        "input_schema": {
            "type": "object",
            "properties": {"award_id": {"type": "integer"}},
            "required": ["award_id"],
        },
    },
    {
        "name": "redeem_award",
        "description": "Redeem points for an award by its id. Fails if the user doesn't have enough points. If the award has break_minutes or dollar_value, those get added to the user's reward banks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "award_id": {"type": "integer"},
                "quantity": {"type": "integer", "description": "How many to redeem at once, 1-99. Defaults to 1."},
            },
            "required": ["award_id"],
        },
    },
    {
        "name": "get_reward_banks",
        "description": "Get the user's current banked break-time (minutes) and $$ balances, accumulated from redeeming break/dollar-type awards.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "spend_break_minutes",
        "description": "Deduct minutes from the user's banked break time (e.g. after they finish a break). Fails if they don't have that much banked.",
        "input_schema": {
            "type": "object",
            "properties": {"minutes": {"type": "integer"}},
            "required": ["minutes"],
        },
    },
    {
        "name": "spend_dollars",
        "description": "Deduct an amount from the user's banked $$ (e.g. when they make a purchase with it). Fails if they don't have that much banked.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "reason": {"type": "string", "description": "What the $$ was spent on."},
            },
            "required": ["amount"],
        },
    },
    {
        "name": "list_dollar_transactions",
        "description": "List the user's most recent $$ bank activity (both money banked from redeeming $$ awards and money spent), newest first.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
    },
]

# Maps tool name -> Python function, used by agent.py to dispatch calls.
DISPATCH = {
    "add_assignment": add_assignment,
    "list_assignments": list_assignments,
    "get_assignment": get_assignment,
    "delete_assignment": delete_assignment,
    "start_assignment": start_assignment,
    "complete_assignment": complete_assignment,
    "add_milestone": add_milestone,
    "list_milestones": list_milestones,
    "toggle_milestone": toggle_milestone,
    "delete_milestone": delete_milestone,
    "get_reward_style": get_reward_style,
    "set_reward_style": set_reward_style,
    "get_preferences": get_preferences,
    "complete_setup": complete_setup,
    "set_additional_rules": set_additional_rules,
    "set_morning_reminders": set_morning_reminders,
    "upsert_recruiting": upsert_recruiting,
    "list_recruiting": list_recruiting,
    "add_points": add_points,
    "get_points_total": get_points_total,
    "list_awards": list_awards,
    "add_award": add_award,
    "deactivate_award": deactivate_award,
    "redeem_award": redeem_award,
    "get_reward_banks": get_reward_banks,
    "spend_break_minutes": spend_break_minutes,
    "spend_dollars": spend_dollars,
    "list_dollar_transactions": list_dollar_transactions,
}
