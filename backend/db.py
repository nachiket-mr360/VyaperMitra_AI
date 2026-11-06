"""SQLite connection, migrations, and atomic transactions."""

from __future__ import annotations

import logging
import sqlite3
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
