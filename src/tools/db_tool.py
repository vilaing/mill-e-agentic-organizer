"""Assignment tracker, recruiting pipeline, and points system.

Each public function here is a "tool" the agent can call. TOOL_SCHEMAS is
what gets sent to the Claude API so it knows these tools exist.
"""
from src.db.db import get_conn


def add_assignment(title: str, course: str = "", due_date: str = "") -> dict:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO assignments (title, course, due_date) VALUES (?, ?, ?)",
        (title, course, due_date),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return {"id": row_id, "title": title, "status": "added"}


def list_assignments(status: str = "open") -> list[dict]:
    conn = get_conn()
    if status == "all":
        rows = conn.execute("SELECT * FROM assignments ORDER BY due_date").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM assignments WHERE status = ? ORDER BY due_date", (status,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def complete_assignment(assignment_id: int) -> dict:
    conn = get_conn()
    conn.execute("UPDATE assignments SET status = 'done' WHERE id = ?", (assignment_id,))
    conn.commit()
    conn.close()
    add_points(reason=f"Completed assignment #{assignment_id}", points=10)
    return {"id": assignment_id, "status": "done"}


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


# --- Tool schemas for the Claude API ---
TOOL_SCHEMAS = [
    {
        "name": "add_assignment",
        "description": "Add a new assignment/task to track, with an optional due date (ISO format, e.g. 2026-08-01).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "course": {"type": "string"},
                "due_date": {"type": "string"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_assignments",
        "description": "List assignments, filtered by status: 'open', 'done', or 'all'.",
        "input_schema": {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": ["open", "done", "all"]}},
        },
    },
    {
        "name": "complete_assignment",
        "description": "Mark an assignment as done by its id. Awards points automatically.",
        "input_schema": {
            "type": "object",
            "properties": {"assignment_id": {"type": "integer"}},
            "required": ["assignment_id"],
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
        "description": "Award reward-system points for a reason (e.g. finishing an assignment early, prepping for an interview).",
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
]

# Maps tool name -> Python function, used by agent.py to dispatch calls.
DISPATCH = {
    "add_assignment": add_assignment,
    "list_assignments": list_assignments,
    "complete_assignment": complete_assignment,
    "upsert_recruiting": upsert_recruiting,
    "list_recruiting": list_recruiting,
    "add_points": add_points,
    "get_points_total": get_points_total,
}
