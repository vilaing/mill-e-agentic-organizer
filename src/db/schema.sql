CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    course TEXT,
    due_date TEXT,                 -- ISO 8601
    status TEXT DEFAULT 'open',    -- open | in_progress | done
    importance INTEGER DEFAULT 3,  -- 1-5, set when created
    difficulty INTEGER DEFAULT 3,  -- 1-5, set when created
    points_earned INTEGER DEFAULT 0, -- running tally toward this assignment's total (start + milestones + completion)
    created_at TEXT DEFAULT (datetime('now'))
);

-- Optional sub-tasks within an assignment (e.g. "HTML page", "stylesheet").
-- When present, they carve out a slice of the assignment's points (see
-- MILESTONE_POOL_FRACTION in db_tool.py) split evenly across however many
-- exist; points_awarded remembers exactly what a milestone earned so
-- unchecking it can cleanly reverse that same amount.
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    done INTEGER DEFAULT 0,
    points_awarded INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (assignment_id) REFERENCES assignments(id)
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
    break_minutes INTEGER DEFAULT 0, -- if >0, redeeming this award banks break time
    dollar_value REAL DEFAULT 0,     -- if >0, redeeming this award banks $$ toward a purchase
    created_at TEXT DEFAULT (datetime('now'))
);

-- Base reward presets. Edit costs/names or deactivate freely -- users can also
-- add their own custom awards via add_award.
INSERT OR IGNORE INTO awards (name, description, cost, is_preset, break_minutes, dollar_value) VALUES
    ('10-minute brain break', 'Step away and do whatever you want for 10 minutes', 5, 1, 10, 0),
    ('$1 towards a for-fun purchase', 'Stack these up towards something you want', 3, 1, 0, 1),
    ('Small snack/drink', 'Grab a small snack or drink', 15, 1, 0, 0),
    ('One hour recreational break', 'An hour to do whatever you want', 25, 1, 60, 0),
    ('Nice meal', 'Treat yourself to a nice meal', 60, 1, 0, 0);

CREATE TABLE IF NOT EXISTS redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    award_id INTEGER NOT NULL,
    points_spent INTEGER NOT NULL,
    redeemed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (award_id) REFERENCES awards(id)
);

-- Single-row table: running balances of break time and $$ banked up from
-- redeeming break/dollar-type awards, spent down as the user uses them.
CREATE TABLE IF NOT EXISTS reward_banks (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    break_minutes INTEGER DEFAULT 0,
    dollars REAL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO reward_banks (id) VALUES (1);

-- History of $$ bank activity: positive amount = banked (from redeeming a
-- $$ award), negative = spent (a purchase).
CREATE TABLE IF NOT EXISTS dollar_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
