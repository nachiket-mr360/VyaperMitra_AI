from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from db import atomic_connection, row_to_dict
from errors import ApiError
from money import (
    line_paise,
    micro_to_units,
    paise_to_rupees,
    rupees_to_paise,
    unit_paise_from_line,
    units_to_micro,
)
from services.stock import apply_stock_change
from timeutil import business_date_str, now_business


def fingerprint_sale(
    items: list[dict[str, Any]],
    *,
    notes: str | None,
    payment_status: str,
    transaction_date: str | None,
) -> str:
    canonical = {
        "items": sorted(
            [
                {
                    "product_id": int(i["product_id"]),
                    "quantity_micro": int(i["quantity_micro"]),
                    "unit_price_paise": int(i["unit_price_paise"]),
                    "line_total_paise": int(i["line_total_paise"]),
                }
                for i in items
            ],
            key=lambda x: (x["product_id"], x["quantity_micro"], x["line_total_paise"]),
        ),
        "notes": notes or "",
        "payment_status": payment_status,
        "transaction_date": transaction_date or "",
    }
    blob = json.dumps(canonical, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _sale_payload(conn: sqlite3.Connection, sale_id: int) -> dict[str, Any]:
    sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale is None:
        raise ApiError("Sale not found", 404, "not_found")
    items = conn.execute(
        """
        SELECT si.*, p.name AS product_name, p.unit
        FROM sale_items si
        JOIN products p ON p.id = si.product_id
        WHERE si.sale_id = ?
        ORDER BY si.id
        """,
        (sale_id,),
    ).fetchall()
    data = row_to_dict(sale)
    assert data is not None
    data["total_amount"] = paise_to_rupees(int(data["total_amount"]))
    data.pop("idempotency_hash", None)
    data["items"] = []
    for item in items:
        d = row_to_dict(item)
        assert d is not None
        d["quantity"] = micro_to_units(int(d["quantity"]))
        d["unit_price"] = paise_to_rupees(int(d["unit_price"]))
        d["line_total"] = paise_to_rupees(int(d["line_total"]))
        data["items"].append(d)
    return data


def get_sale(sale_id: int) -> dict[str, Any]:
    from services.sale_lifecycle import get_sale_detail

    return get_sale_detail(sale_id)


def list_sales(
    *,
    on_date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sale_id: int | None = None,
) -> list[dict[str, Any]]:
    from services.sale_lifecycle import list_sales as _list

    return _list(on_date=on_date, date_from=date_from, date_to=date_to, sale_id=sale_id)


def _normalize_items(raw_items: list[dict[str, Any]]) -> list[dict[str, int]]:
    out: list[dict[str, int]] = []
    for raw in raw_items:
        product_id = int(raw["product_id"])
        quantity_micro = units_to_micro(raw["quantity"], "quantity")
        if quantity_micro <= 0:
            raise ApiError("quantity must be greater than 0", 400, "invalid_value")
        if "line_total" in raw and raw["line_total"] is not None:
            line_total_paise = rupees_to_paise(raw["line_total"], "line_total")
            unit_price_paise = unit_paise_from_line(quantity_micro, line_total_paise)
        else:
            unit_price_paise = rupees_to_paise(raw["unit_price"], "unit_price")
            line_total_paise = line_paise(quantity_micro, unit_price_paise)
        out.append(
            {
                "product_id": product_id,
                "quantity_micro": quantity_micro,
                "unit_price_paise": unit_price_paise,
                "line_total_paise": line_total_paise,
            }
        )
    return out


def create_sale(
    items: list[dict[str, Any]],
    *,
    idempotency_key: str | None,
    notes: str | None,
    payment_status: str = "unknown",
    transaction_date: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> tuple[dict[str, Any], bool]:
    if not items:
        raise ApiError("Sale requires at least one item", 400, "missing_field")
    if payment_status not in {"unknown", "paid", "unpaid", "partial"}:
        raise ApiError("Invalid payment_status", 400, "invalid_value")

    normalized = _normalize_items(items)
    digest = fingerprint_sale(
        normalized,
        notes=notes,
        payment_status=payment_status,
        transaction_date=transaction_date,
    )

    def _run(conn: sqlite3.Connection) -> tuple[dict[str, Any], bool]:
        if idempotency_key:
            existing = conn.execute(
                "SELECT id, idempotency_hash FROM sales WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                stored = existing["idempotency_hash"]
                if stored and stored != digest:
                    raise ApiError(
                        "Idempotency key already used with a different sale",
                        409,
                        "idempotency_conflict",
                    )
                from services.sale_lifecycle import sale_detail

                return sale_detail(conn, int(existing["id"])), True

        now = now_business()
        day = transaction_date or business_date_str(now)
        created = now.isoformat()
        total_paise = sum(i["line_total_paise"] for i in normalized)

        for item in normalized:
            product = conn.execute(
                "SELECT id, current_stock, active, stock_known FROM products WHERE id = ?",
                (item["product_id"],),
            ).fetchone()
            if product is None:
                raise ApiError(f"Product {item['product_id']} not found", 404, "not_found")
            if not product["active"]:
                raise ApiError("Cannot sell an inactive product", 409, "inactive_product")
            if bool(product["stock_known"]) and int(product["current_stock"]) < item["quantity_micro"]:
                raise ApiError("Insufficient stock", 409, "insufficient_stock")

        try:
            cur = conn.execute(
                """
                INSERT INTO sales (
                    transaction_date, total_amount, payment_status, notes,
                    idempotency_key, idempotency_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (day, total_paise, payment_status, notes, idempotency_key, digest, created),
            )
        except sqlite3.IntegrityError:
            again = conn.execute(
                "SELECT id, idempotency_hash FROM sales WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if again:
                if again["idempotency_hash"] and again["idempotency_hash"] != digest:
                    raise ApiError(
                        "Idempotency key already used with a different sale",
                        409,
                        "idempotency_conflict",
                    ) from None
                from services.sale_lifecycle import sale_detail

                return sale_detail(conn, int(again["id"])), True
            raise ApiError("Could not record sale", 409, "conflict") from None

        sale_id = int(cur.lastrowid)
        for item in normalized:
            cur_item = conn.execute(
                """
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    sale_id,
                    item["product_id"],
                    item["quantity_micro"],
                    item["unit_price_paise"],
                    item["line_total_paise"],
                ),
            )
            item_id = int(cur_item.lastrowid)
            conn.execute(
                """
                INSERT INTO sale_lines (sale_id, line_key, origin_sale_item_id, added, removed, created_at)
                VALUES (?, ?, ?, 0, 0, ?)
                """,
                (sale_id, str(uuid.uuid4()), item_id, created),
            )
            known = conn.execute(
                "SELECT stock_known FROM products WHERE id = ?",
                (item["product_id"],),
            ).fetchone()
            if known and int(known["stock_known"]):
                apply_stock_change(
                    conn,
                    item["product_id"],
                    movement_type="sale",
                    delta_micro=-item["quantity_micro"],
                    unit_cost_paise=None,
                    notes=f"sale:{sale_id}",
                )
        from services.sale_lifecycle import sale_detail

        return sale_detail(conn, sale_id), False

    if conn is not None:
        return _run(conn)
    with atomic_connection() as owned:
        return _run(owned)
