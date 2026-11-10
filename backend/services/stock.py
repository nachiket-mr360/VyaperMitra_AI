from __future__ import annotations

import sqlite3
from typing import Any

from db import atomic_connection, row_to_dict
from errors import ApiError
from money import micro_to_units, paise_to_rupees, rupees_to_paise, units_to_micro
from timeutil import now_business

ALLOWED_MOVEMENTS = frozenset(
    {
        "opening",
        "purchase",
        "sale",
        "adjustment",
        "sale_return",
        "sale_correction",
        "sale_cancel",
    }
)


def apply_stock_change(
    conn: sqlite3.Connection,
    product_id: int,
    *,
    movement_type: str,
    delta_micro: int,
    unit_cost_paise: int | None,
    notes: str | None,
    ref_sale_id: int | None = None,
    ref_line_key: str | None = None,
    ref_kind: str | None = None,
) -> dict[str, Any]:
    if movement_type not in ALLOWED_MOVEMENTS:
        raise ApiError("Invalid movement type", 400, "invalid_value")
    if delta_micro == 0:
        raise ApiError("quantity cannot be zero", 400, "invalid_value")
    row = conn.execute(
        "SELECT id FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    if row is None:
        raise ApiError("Product not found", 404, "not_found")
    now = now_business().isoformat()
    cur = conn.execute(
        """
        UPDATE products
        SET current_stock = current_stock + ?, updated_at = ?,
            stock_known = CASE WHEN ? > 0 THEN 1 ELSE stock_known END
        WHERE id = ? AND current_stock + ? >= 0
        """,
        (delta_micro, now, delta_micro, product_id, delta_micro),
    )
    if cur.rowcount != 1:
        raise ApiError("Insufficient stock", 409, "insufficient_stock")
    stock_row = conn.execute(
        "SELECT current_stock FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    new_stock = int(stock_row["current_stock"])
    cur = conn.execute(
        """
        INSERT INTO stock_movements (
            product_id, movement_type, quantity, unit_cost, notes, created_at,
            ref_sale_id, ref_line_key, ref_kind
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            movement_type,
            delta_micro,
            unit_cost_paise,
            notes,
            now,
            ref_sale_id,
            ref_line_key,
            ref_kind,
        ),
    )
    movement = conn.execute(
        "SELECT * FROM stock_movements WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    data = _movement_api(movement)
    data["current_stock"] = micro_to_units(new_stock)
    return data


def _movement_api(row: sqlite3.Row) -> dict[str, Any]:
    data = row_to_dict(row)
    assert data is not None
    data["quantity"] = micro_to_units(int(data["quantity"]))
    if data["unit_cost"] is not None:
        data["unit_cost"] = paise_to_rupees(int(data["unit_cost"]))
    return data


def record_opening(product_id: int, quantity: Any, unit_cost: Any, notes: str | None) -> dict:
    micro = units_to_micro(quantity, "quantity")
    if micro <= 0:
        raise ApiError("quantity must be greater than 0", 400, "invalid_value")
    cost = rupees_to_paise(unit_cost, "unit_cost") if unit_cost is not None else None
    with atomic_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM stock_movements WHERE product_id = ? AND movement_type = 'opening'",
            (product_id,),
        ).fetchone()
        if existing:
            raise ApiError("Opening stock already recorded for this product", 409, "duplicate")
        return apply_stock_change(
            conn,
            product_id,
            movement_type="opening",
            delta_micro=micro,
            unit_cost_paise=cost,
            notes=notes,
        )


def record_purchase(
    product_id: int,
    quantity: Any,
    unit_cost: Any,
    notes: str | None,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict:
    micro = units_to_micro(quantity, "quantity")
    if micro <= 0:
        raise ApiError("quantity must be greater than 0", 400, "invalid_value")
    cost = rupees_to_paise(unit_cost, "unit_cost") if unit_cost is not None else None

    def _run(c: sqlite3.Connection) -> dict:
        return apply_stock_change(
            c,
            product_id,
            movement_type="purchase",
            delta_micro=micro,
            unit_cost_paise=cost,
            notes=notes,
        )

    if conn is not None:
        return _run(conn)
    with atomic_connection() as owned:
        return _run(owned)


def record_adjustment(product_id: int, quantity: Any, notes: str | None) -> dict:
    micro = units_to_micro(quantity, "quantity")
    if micro == 0:
        raise ApiError("quantity cannot be zero", 400, "invalid_value")
    with atomic_connection() as conn:
        return apply_stock_change(
            conn,
            product_id,
            movement_type="adjustment",
            delta_micro=micro,
            unit_cost_paise=None,
            notes=notes,
        )


def list_stock(*, low_only: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT id, name, unit, current_stock, low_stock_threshold, active, stock_known
        FROM products
        WHERE active = 1
    """
    if low_only:
        sql += " AND stock_known = 1 AND current_stock <= low_stock_threshold"
    sql += " ORDER BY name COLLATE NOCASE"
    with atomic_connection() as conn:
        rows = conn.execute(sql).fetchall()
        out = []
        for r in rows:
            item = row_to_dict(r)
            assert item is not None
            item["active"] = bool(item["active"])
            known = bool(item.get("stock_known", 1))
            item["stock_known"] = known
            item["current_stock"] = micro_to_units(int(item["current_stock"])) if known else None
            item["low_stock_threshold"] = micro_to_units(int(item["low_stock_threshold"]))
            item["low_stock"] = known and int(r["current_stock"]) <= int(r["low_stock_threshold"])
            out.append(item)
        return out


def list_movements(product_id: int | None = None) -> list[dict[str, Any]]:
    with atomic_connection() as conn:
        if product_id is None:
            rows = conn.execute(
                """
                SELECT m.*, p.name AS product_name, p.unit
                FROM stock_movements m
                JOIN products p ON p.id = m.product_id
                ORDER BY m.id DESC
                """
            ).fetchall()
        else:
            exists = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
            if exists is None:
                raise ApiError("Product not found", 404, "not_found")
            rows = conn.execute(
                """
                SELECT m.*, p.name AS product_name, p.unit
                FROM stock_movements m
                JOIN products p ON p.id = m.product_id
                WHERE m.product_id = ?
                ORDER BY m.id DESC
                """,
                (product_id,),
            ).fetchall()
        return [_movement_api(r) for r in rows]
