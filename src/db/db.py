"""SQLite helper. Run `python -m src.db.db init` to create/update the database."""
import sqlite3
import sys
from contextvars import ContextVar, Token
from pathlib import Path
from src.config import DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Lets one request point every tool at its own database file (see src/demo.py)
# without threading a path through each tool function. None means DB_PATH.
_db_path_override: ContextVar[str | None] = ContextVar("db_path_override", default=None)


def use_db(path: str) -> Token:
    """Route get_conn() to `path` in this context; undo with reset_db(token)."""
    return _db_path_override.set(path)


def reset_db(token: Token) -> None:
    _db_path_override.reset(token)


# Columns added after the initial schema. Applied as ALTER TABLE so existing
# databases (with existing data) get upgraded instead of wiped.
MIGRATIONS = [
    "ALTER TABLE assignments ADD COLUMN importance INTEGER DEFAULT 3",
    "ALTER TABLE assignments ADD COLUMN difficulty INTEGER DEFAULT 3",
    "ALTER TABLE preferences ADD COLUMN additional_rules TEXT DEFAULT ''",
    "ALTER TABLE preferences ADD COLUMN morning_reminders INTEGER DEFAULT 1",
    "ALTER TABLE preferences ADD COLUMN onboarding_completed INTEGER DEFAULT 0",
    "ALTER TABLE awards ADD COLUMN break_minutes INTEGER DEFAULT 0",
    "ALTER TABLE awards ADD COLUMN dollar_value REAL DEFAULT 0",
    "ALTER TABLE assignments ADD COLUMN points_earned INTEGER DEFAULT 0",
    "ALTER TABLE milestones ADD COLUMN point_percent INTEGER",
    "ALTER TABLE preferences ADD COLUMN points_on_start INTEGER DEFAULT 1",
    "ALTER TABLE preferences ADD COLUMN points_on_milestones INTEGER DEFAULT 1",
    "ALTER TABLE preferences ADD COLUMN points_on_completion INTEGER DEFAULT 1",
    "ALTER TABLE preferences ADD COLUMN point_rules_summary TEXT DEFAULT ''",
]


def get_conn():
    path = _db_path_override.get() or DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    # Migrations first: on an existing DB they backfill columns that
    # schema.sql's INSERTs may already reference explicitly. On a fresh DB
    # every statement here harmlessly no-ops (table doesn't exist yet) since
    # schema.sql's CREATE TABLEs already include these columns directly.
    for stmt in MIGRATIONS:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists, or table doesn't exist yet
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_db()
        print(f"Initialized/updated database at {DB_PATH}")
    else:
        print("Usage: python -m src.db.db init")
