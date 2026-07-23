CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    course TEXT,
    due_date TEXT,              -- ISO 8601
    status TEXT DEFAULT 'open', -- open | done | overdue
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recruiting (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    role TEXT,
    stage TEXT DEFAULT 'applied', -- applied | oa | interview | offer | rejected
    next_action TEXT,
    next_action_date TEXT,
    notes TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS points_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reason TEXT NOT NULL,
    points INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
