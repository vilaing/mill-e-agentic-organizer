"""SQLite helper. Run `python -m src.db.db init` to create the database."""
import sqlite3
import sys
from pathlib import Path
from src.config import DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print(f"Initialized database at {DB_PATH}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_db()
    else:
        print("Usage: python -m src.db.db init")
