CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    due_time TEXT,
    due_at TEXT NOT NULL,
    recurrence TEXT NOT NULL DEFAULT 'none',
    weekday INTEGER,
    month_day INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    language TEXT NOT NULL DEFAULT 'en',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (status, due_at);
CREATE INDEX IF NOT EXISTS idx_reminders_date ON reminders (due_date);

CREATE TABLE IF NOT EXISTS shop_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_shop_notes_created ON shop_notes (created_at);
