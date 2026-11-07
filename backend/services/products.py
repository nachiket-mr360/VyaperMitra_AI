from __future__ import annotations

import sqlite3
from typing import Any

from db import atomic_connection, row_to_dict
from errors import ApiError
from money import micro_to_units, rupees_to_paise, units_to_micro
from timeutil import now_business
from validate import normalize_text, require_unit


def _now() -> str:
    return now_business().isoformat()


def product_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = row_to_dict(row)
    assert data is not None
    data["active"] = bool(data["active"])
    data["current_stock"] = micro_to_units(int(data["current_stock"]))
    data["low_stock_threshold"] = micro_to_units(int(data["low_stock_threshold"]))
    data["low_stock"] = int(row["current_stock"]) <= int(row["low_stock_threshold"])
    return data


def get_product(conn: sqlite3.Connection, product_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise ApiError("Product not found", 404, "not_found")
    return row


def create_product(
    name: str,
    unit: str,
    low_stock_threshold: Any = 0,
    opening_stock: Any | None = None,
    opening_unit_cost: Any | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    normalized = normalize_text(name)
    unit_n = require_unit(unit)
    threshold_micro = units_to_micro(low_stock_threshold, "low_stock_threshold")
    if threshold_micro < 0:
        raise ApiError("low_stock_threshold cannot be negative", 400, "invalid_value")
    now = _now()

    def _run(conn: sqlite3.Connection) -> dict[str, Any]:
        exists = conn.execute(
            "SELECT id FROM products WHERE normalized_name = ?", (normalized,)
        ).fetchone()
        if exists:
            raise ApiError("A product with this name already exists", 409, "duplicate")
        alias_hit = conn.execute(
            "SELECT product_id FROM product_aliases WHERE normalized_alias = ?",
            (normalized,),
        ).fetchone()
        if alias_hit:
            raise ApiError("This name is already used as an alias", 409, "duplicate")
        cur = conn.execute(
            """
            INSERT INTO products (
                name, normalized_name, unit, current_stock, low_stock_threshold,
                active, created_at, updated_at
            ) VALUES (?, ?, ?, 0, ?, 1, ?, ?)
            """,
            (name.strip(), normalized, unit_n, threshold_micro, now, now),
        )
        product_id = int(cur.lastrowid)
        if opening_stock is not None:
            from services.stock import apply_stock_change

            micro = units_to_micro(opening_stock, "opening_stock")
            if micro <= 0:
                raise ApiError("opening_stock must be greater than 0", 400, "invalid_value")
            cost = (
                rupees_to_paise(opening_unit_cost, "opening_unit_cost")
                if opening_unit_cost is not None
                else None
            )
            apply_stock_change(
                conn,
                product_id,
                movement_type="opening",
                delta_micro=micro,
                unit_cost_paise=cost,
                notes="opening stock",
            )
        row = get_product(conn, product_id)
        return product_dict(row)

    if conn is not None:
        return _run(conn)
    with atomic_connection() as owned:
        return _run(owned)


def list_products(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    with atomic_connection() as conn:
        if include_inactive:
            rows = conn.execute("SELECT * FROM products ORDER BY name COLLATE NOCASE").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM products WHERE active = 1 ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [product_dict(r) for r in rows]


def get_product_detail(product_id: int) -> dict[str, Any]:
    with atomic_connection() as conn:
        row = get_product(conn, product_id)
        data = product_dict(row)
        aliases = conn.execute(
            "SELECT id, alias, language, created_at FROM product_aliases WHERE product_id = ? ORDER BY id",
            (product_id,),
        ).fetchall()
        data["aliases"] = [row_to_dict(a) for a in aliases]
        return data


def update_product(product_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    with atomic_connection() as conn:
        get_product(conn, product_id)
        sets: list[str] = []
        values: list[Any] = []
        if "name" in fields:
            name = fields["name"]
            normalized = normalize_text(name)
            clash = conn.execute(
                "SELECT id FROM products WHERE normalized_name = ? AND id != ?",
                (normalized, product_id),
            ).fetchone()
            if clash:
                raise ApiError("A product with this name already exists", 409, "duplicate")
            sets.extend(["name = ?", "normalized_name = ?"])
            values.extend([name.strip(), normalized])
        if "unit" in fields:
            sets.append("unit = ?")
            values.append(require_unit(fields["unit"]))
        if "low_stock_threshold" in fields:
            sets.append("low_stock_threshold = ?")
            values.append(units_to_micro(fields["low_stock_threshold"], "low_stock_threshold"))
        if "active" in fields:
            sets.append("active = ?")
            values.append(1 if fields["active"] else 0)
        if not sets:
            raise ApiError("No fields to update", 400, "missing_field")
        sets.append("updated_at = ?")
        values.append(_now())
        values.append(product_id)
        conn.execute(f"UPDATE products SET {', '.join(sets)} WHERE id = ?", values)
        return product_dict(get_product(conn, product_id))


def deactivate_product(product_id: int) -> dict[str, Any]:
    return update_product(product_id, {"active": False})


def add_alias(product_id: int, alias: str, language: str = "und") -> dict[str, Any]:
    normalized = normalize_text(alias)
    now = _now()
    with atomic_connection() as conn:
        get_product(conn, product_id)
        name_hit = conn.execute(
            "SELECT id FROM products WHERE normalized_name = ?", (normalized,)
        ).fetchone()
        if name_hit:
            raise ApiError("Alias matches an existing product name", 409, "duplicate")
        try:
            cur = conn.execute(
                """
                INSERT INTO product_aliases (product_id, alias, normalized_alias, language, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (product_id, alias.strip(), normalized, language.strip() or "und", now),
            )
        except sqlite3.IntegrityError:
            raise ApiError("This alias already exists", 409, "duplicate") from None
        row = conn.execute(
            "SELECT id, product_id, alias, language, created_at FROM product_aliases WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        return row_to_dict(row)  # type: ignore[return-value]
