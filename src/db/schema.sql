CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    course TEXT,
    due_date TEXT,                 -- ISO 8601
    status TEXT DEFAULT 'open',    -- open | in_progress | done
    importance INTEGER DEFAULT 3,  -- 1-5, set when created
    difficulty INTEGER DEFAULT 3,  -- 1-5, set when created
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

-- Single-row table: how points get split between starting vs finishing a task,
-- plus any custom rules and reminder preferences gathered during setup.
CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    reward_style TEXT DEFAULT 'balanced', -- mostly_encouragement | balanced | mostly_completion
    additional_rules TEXT DEFAULT '',     -- freeform custom instructions from the user
    morning_reminders INTEGER DEFAULT 1,  -- 1 = opted in, 0 = opted out
    onboarding_completed INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO preferences (id, reward_style) VALUES (1, 'balanced');

CREATE TABLE IF NOT EXISTS awards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    cost INTEGER NOT NULL,
    is_preset INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Base reward presets. Edit costs/names or deactivate freely -- users can also
-- add their own custom awards via add_award.
INSERT OR IGNORE INTO awards (name, description, cost, is_preset) VALUES
    ('10-minute brain break', 'Step away and do whatever you want for 10 minutes', 5, 1),
    ('$1 towards a for-fun purchase', 'Stack these up towards something you want', 3, 1),
    ('Small snack/drink', 'Grab a small snack or drink', 15, 1),
    ('One hour recreational break', 'An hour to do whatever you want', 25, 1),
    ('Nice meal', 'Treat yourself to a nice meal', 60, 1);

CREATE TABLE IF NOT EXISTS redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    award_id INTEGER NOT NULL,
    points_spent INTEGER NOT NULL,
    redeemed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (award_id) REFERENCES awards(id)
);
