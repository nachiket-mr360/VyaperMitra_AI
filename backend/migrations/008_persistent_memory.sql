-- Additive. Does not alter products, sales, stock, reminders, or pending_voice_actions.
-- One SQLite file remains one shop DB; shop_id isolates rows if multiple identities share a file.

CREATE TABLE IF NOT EXISTS personal_memories (
    id TEXT PRIMARY KEY,
    shop_id TEXT NOT NULL,
    mem_key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_memories_active
    ON personal_memories (shop_id, mem_key) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_personal_memories_shop
    ON personal_memories (shop_id, status);

CREATE TABLE IF NOT EXISTS business_memories (
    id TEXT PRIMARY KEY,
    shop_id TEXT NOT NULL,
    mem_key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_business_memories_active
    ON business_memories (shop_id, mem_key) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_business_memories_shop
    ON business_memories (shop_id, status);
