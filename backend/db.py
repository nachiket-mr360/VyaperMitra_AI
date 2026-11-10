"""SQLite connection, migrations, and atomic transactions."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from config import Config
from timeutil import now_business

logger = logging.getLogger("vyaparmitra.db")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def get_connection(*, immediate: bool = False) -> sqlite3.Connection:
    path = Path(Config.DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.isolation_level = None
    if immediate:
        conn.execute("BEGIN IMMEDIATE")
    return conn


@contextmanager
def atomic_connection(*, immediate: bool = True):
    conn = get_connection(immediate=immediate)
    try:
        yield conn
        if immediate and conn.in_transaction:
            conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        raise
    finally:
        conn.close()


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not row:
        return set()
    return {int(r["version"]) for r in conn.execute("SELECT version FROM schema_migrations")}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _apply_003_data(conn: sqlite3.Connection) -> None:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "sales" in tables:
        cols = _table_columns(conn, "sales")
        if "idempotency_hash" not in cols:
            conn.execute("ALTER TABLE sales ADD COLUMN idempotency_hash TEXT")
    encoded = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'money_encoding'"
    ).fetchone()
    if encoded and encoded["value"] == "integer_minor":
        return
    count = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    if count:
        logger.info("Converting REAL money/qty columns to integer minor units")
        conn.execute(
            """
            UPDATE products SET
                current_stock = CAST(ROUND(current_stock * 1000000) AS INTEGER),
                low_stock_threshold = CAST(ROUND(low_stock_threshold * 1000000) AS INTEGER)
            """
        )
        conn.execute(
            """
            UPDATE stock_movements SET
                quantity = CAST(ROUND(quantity * 1000000) AS INTEGER),
                unit_cost = CASE
                    WHEN unit_cost IS NULL THEN NULL
                    ELSE CAST(ROUND(unit_cost * 100) AS INTEGER)
                END
            """
        )
        conn.execute(
            "UPDATE sales SET total_amount = CAST(ROUND(total_amount * 100) AS INTEGER)"
        )
        conn.execute(
            """
            UPDATE sale_items SET
                quantity = CAST(ROUND(quantity * 1000000) AS INTEGER),
                unit_price = CAST(ROUND(unit_price * 100) AS INTEGER),
                line_total = CAST(ROUND(line_total * 100) AS INTEGER)
            """
        )
    conn.execute(
        "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('money_encoding', 'integer_minor')"
    )


def _backup_before_009(conn: sqlite3.Connection) -> None:
    path = Path(Config.DATABASE_PATH)
    if str(path) in {":memory:", ""} or not path.exists():
        return
    dest = path.with_name(path.name + ".pre-009.bak")
    if dest.exists():
        return
    try:
        conn.execute("PRAGMA wal_checkpoint(FULL)")
    except sqlite3.Error:
        pass
    dest_conn = sqlite3.connect(str(dest))
    try:
        conn.backup(dest_conn)
    finally:
        dest_conn.close()
    logger.info("Wrote pre-009 backup %s", dest)


def _apply_009(conn: sqlite3.Connection) -> None:
    """sale_lines, events, sales.status, stock_movements rebuild. Restores FK pragma always."""
    _backup_before_009(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        cols = _table_columns(conn, "sales")
        if "status" not in cols:
            conn.execute("ALTER TABLE sales ADD COLUMN status TEXT NOT NULL DEFAULT 'open'")
        if "cancelled_at" not in cols:
            conn.execute("ALTER TABLE sales ADD COLUMN cancelled_at TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_sale_items_id_sale ON sale_items (id, sale_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sale_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL REFERENCES sales (id),
                line_key TEXT NOT NULL,
                origin_sale_item_id INTEGER UNIQUE,
                added INTEGER NOT NULL DEFAULT 0 CHECK (added IN (0, 1)),
                removed INTEGER NOT NULL DEFAULT 0 CHECK (removed IN (0, 1)),
                created_at TEXT NOT NULL,
                UNIQUE (sale_id, line_key),
                CHECK (
                    (added = 0 AND origin_sale_item_id IS NOT NULL)
                    OR (added = 1 AND origin_sale_item_id IS NULL)
                ),
                FOREIGN KEY (origin_sale_item_id, sale_id) REFERENCES sale_items (id, sale_id)
            )
            """
        )
        existing_lines = conn.execute("SELECT COUNT(*) AS c FROM sale_lines").fetchone()["c"]
        items = conn.execute("SELECT id, sale_id FROM sale_items ORDER BY id").fetchall()
        if existing_lines == 0 and items:
            now = now_business().isoformat()
            for row in items:
                conn.execute(
                    """
                    INSERT INTO sale_lines (sale_id, line_key, origin_sale_item_id, added, removed, created_at)
                    VALUES (?, ?, ?, 0, 0, ?)
                    """,
                    (int(row["sale_id"]), str(uuid.uuid4()), int(row["id"]), now),
                )
            n_lines = conn.execute("SELECT COUNT(*) AS c FROM sale_lines").fetchone()["c"]
            n_items = conn.execute("SELECT COUNT(*) AS c FROM sale_items").fetchone()["c"]
            if int(n_lines) != int(n_items):
                raise sqlite3.Error("sale_lines backfill count mismatch")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sale_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                line_key TEXT NOT NULL,
                added INTEGER NOT NULL DEFAULT 0 CHECK (added IN (0, 1)),
                removed INTEGER NOT NULL DEFAULT 0 CHECK (removed IN (0, 1)),
                product_id INTEGER NOT NULL REFERENCES products (id),
                quantity INTEGER NOT NULL,
                unit_price INTEGER NOT NULL,
                line_total INTEGER NOT NULL,
                before_json TEXT NOT NULL,
                after_json TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                idempotency_hash TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sale_id, line_key) REFERENCES sale_lines (sale_id, line_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sale_returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL,
                line_key TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price INTEGER NOT NULL,
                line_total INTEGER NOT NULL,
                idempotency_key TEXT UNIQUE,
                idempotency_hash TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (sale_id, line_key) REFERENCES sale_lines (sale_id, line_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sale_cancellations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER NOT NULL UNIQUE REFERENCES sales (id),
                reversal_paise INTEGER NOT NULL,
                idempotency_key TEXT UNIQUE,
                idempotency_hash TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        _rebuild_stock_movements_009(conn)
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise sqlite3.Error(f"foreign_key_check failed: {bad[:5]}")
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        if int(on) != 1:
            raise sqlite3.Error("foreign_keys pragma is not ON after 009")


def _rebuild_stock_movements_009(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE stock_movements_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products (id),
            movement_type TEXT NOT NULL CHECK (
                movement_type IN (
                    'opening', 'purchase', 'sale', 'adjustment',
                    'sale_return', 'sale_correction', 'sale_cancel'
                )
            ),
            quantity INTEGER NOT NULL CHECK (quantity != 0),
            unit_cost INTEGER CHECK (unit_cost IS NULL OR unit_cost >= 0),
            notes TEXT,
            created_at TEXT NOT NULL,
            ref_sale_id INTEGER,
            ref_line_key TEXT,
            ref_kind TEXT
        )
        """
    )
    old_n = conn.execute("SELECT COUNT(*) AS c FROM stock_movements").fetchone()["c"]
    conn.execute(
        """
        INSERT INTO stock_movements_new (
            id, product_id, movement_type, quantity, unit_cost, notes, created_at,
            ref_sale_id, ref_line_key, ref_kind
        )
        SELECT id, product_id, movement_type, quantity, unit_cost, notes, created_at,
               NULL, NULL, NULL
        FROM stock_movements
        """
    )
    new_n = conn.execute("SELECT COUNT(*) AS c FROM stock_movements_new").fetchone()["c"]
    if int(old_n) != int(new_n):
        raise sqlite3.Error("stock_movements copy count mismatch")
    conn.execute("DROP TABLE stock_movements")
    conn.execute("ALTER TABLE stock_movements_new RENAME TO stock_movements")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements (product_id, created_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_movements_type ON stock_movements (movement_type)")
    mx = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM stock_movements").fetchone()["m"]
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'stock_movements'")
        if int(mx):
            conn.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES ('stock_movements', ?)",
                (int(mx),),
            )
    except sqlite3.Error:
        pass


def apply_migrations(conn: sqlite3.Connection) -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    applied = _applied_versions(conn)
    now = now_business().isoformat()
    for path in files:
        version = int(path.name.split("_", 1)[0])
        if version in applied:
            continue
        logger.info("Applying migration %s", path.name)
        conn.executescript(path.read_text(encoding="utf-8"))
        if version == 3:
            _apply_003_data(conn)
        if version == 6:
            from catalog import seed_aliases_for_existing

            seed_aliases_for_existing(conn)
        if version == 9:
            _apply_009(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, path.name, now),
        )
        applied.add(version)


def init_db() -> None:
    with atomic_connection(immediate=False) as conn:
        apply_migrations(conn)
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
            ("schema_phase", "2"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
            ("business_timezone", Config.BUSINESS_TIMEZONE),
        )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}
