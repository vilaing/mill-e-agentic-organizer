"""SQLite helper. Run `python -m src.db.db init` to create/update the database."""
import sqlite3
import sys
from pathlib import Path
from src.config import DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

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
]


def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
    print(f"Initialized/updated database at {DB_PATH}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_db()
    else:
        print("Usage: python -m src.db.db init")
