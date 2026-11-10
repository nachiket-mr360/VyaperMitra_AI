from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from typing import Any

from db import atomic_connection, row_to_dict
from errors import ApiError
from money import line_paise, micro_to_units, paise_to_rupees, rupees_to_paise, units_to_micro
from services.stock import apply_stock_change
from timeutil import now_business


def _digest(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _replay(conn: sqlite3.Connection, table: str, key: str | None, digest: str) -> dict[str, Any] | None:
    if not key:
        return None
    row = conn.execute(
        f"SELECT id, idempotency_hash, sale_id FROM {table} WHERE idempotency_key = ?",
        (key,),
    ).fetchone()
    if not row:
        return None
    if row["idempotency_hash"] and row["idempotency_hash"] != digest:
        raise ApiError("Idempotency key already used with a different payload", 409, "idempotency_conflict")
    return sale_detail(conn, int(row["sale_id"]))


def _lines_state(conn: sqlite3.Connection, sale_id: int) -> list[dict[str, Any]]:
    lines = conn.execute(
        "SELECT * FROM sale_lines WHERE sale_id = ? ORDER BY id",
        (sale_id,),
    ).fetchall()
    items = {
        int(r["id"]): r
        for r in conn.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall()
    }
    corrections = conn.execute(
        "SELECT * FROM sale_corrections WHERE sale_id = ? ORDER BY id",
        (sale_id,),
    ).fetchall()
    returns = conn.execute(
        "SELECT * FROM sale_returns WHERE sale_id = ? ORDER BY id",
        (sale_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for ln in lines:
        key = ln["line_key"]
        origin_id = ln["origin_sale_item_id"]
        orig = items.get(int(origin_id)) if origin_id is not None else None
        product_id = int(orig["product_id"]) if orig else None
        qty = int(orig["quantity"]) if orig else 0
        unit_price = int(orig["unit_price"]) if orig else 0
        line_total = int(orig["line_total"]) if orig else 0
        original_qty = qty
        original_total = line_total
        removed = bool(ln["removed"])
        for c in corrections:
            if c["line_key"] != key:
                continue
            product_id = int(c["product_id"])
            qty = int(c["quantity"])
            unit_price = int(c["unit_price"])
            line_total = int(c["line_total"])
            removed = bool(c["removed"])
        ret_qty = 0
        ret_amt = 0
        for r in returns:
            if r["line_key"] != key:
                continue
            ret_qty += int(r["quantity"])
            ret_amt += int(r["line_total"])
        remaining = max(0, qty - ret_qty)
        name = None
        unit = None
        if product_id:
            p = conn.execute("SELECT name, unit FROM products WHERE id = ?", (product_id,)).fetchone()
            if p:
                name, unit = p["name"], p["unit"]
        out.append(
            {
                "line_key": key,
                "origin_sale_item_id": int(origin_id) if origin_id is not None else None,
                "added": bool(ln["added"]),
                "removed": removed,
                "product_id": product_id,
                "product_name": name,
                "unit": unit,
                "original_quantity": micro_to_units(original_qty) if orig else 0,
                "effective_quantity": micro_to_units(qty),
                "returned_quantity": micro_to_units(ret_qty),
                "remaining_quantity": micro_to_units(remaining),
                "unit_price": paise_to_rupees(unit_price),
                "original_line_total": paise_to_rupees(original_total) if orig else 0,
                "effective_line_gross_paise": line_total,
                "returned_amount_paise": ret_amt,
                "remaining_micro": remaining,
                "effective_qty_micro": qty,
                "returned_qty_micro": ret_qty,
                "unit_price_paise": unit_price,
                "product_id_int": product_id,
            }
        )
    return out


def _financials(conn: sqlite3.Connection, sale_id: int, status: str, lines: list[dict[str, Any]]) -> dict[str, Any]:
    sale = conn.execute("SELECT total_amount FROM sales WHERE id = ?", (sale_id,)).fetchone()
    original = int(sale["total_amount"])
    gross = sum(int(x["effective_line_gross_paise"]) for x in lines if not x["removed"])
    if any(x["removed"] for x in lines):
        gross = sum(int(x["effective_line_gross_paise"]) for x in lines if not x["removed"])
    returns_amt = sum(int(x["returned_amount_paise"]) for x in lines)
    corr_adj = gross - original
    if status == "cancelled":
        remaining_net = gross - returns_amt
        cancel_rev = -remaining_net
        net = 0
    else:
        cancel_rev = 0
        net = gross - returns_amt
    return {
        "original_recorded": paise_to_rupees(original),
        "correction_adjustment": paise_to_rupees(corr_adj),
        "return_amount": paise_to_rupees(returns_amt),
        "cancellation_reversal": paise_to_rupees(cancel_rev),
        "net_recorded": paise_to_rupees(net),
        "net_recorded_paise": net,
        "cash_received": None,
        "cash_refunded": None,
        "outstanding": None,
    }


def sale_detail(conn: sqlite3.Connection, sale_id: int) -> dict[str, Any]:
    sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale is None:
        raise ApiError("Sale not found", 404, "not_found")
    data = row_to_dict(sale)
    assert data is not None
    data.pop("idempotency_hash", None)
    status = data.get("status") or "open"
    lines = _lines_state(conn, sale_id)
    data["total_amount"] = paise_to_rupees(int(sale["total_amount"]))
    data["status"] = status
    data["lines"] = [
        {
            "line_key": x["line_key"],
            "product_id": x["product_id"],
            "product_name": x["product_name"],
            "unit": x["unit"],
            "original_quantity": x["original_quantity"],
            "effective_quantity": x["effective_quantity"],
            "returned_quantity": x["returned_quantity"],
            "remaining_quantity": x["remaining_quantity"],
            "unit_price": x["unit_price"],
            "added": x["added"],
            "removed": x["removed"],
        }
        for x in lines
    ]
    items = conn.execute(
        """
        SELECT si.*, p.name AS product_name, p.unit
        FROM sale_items si JOIN products p ON p.id = si.product_id
        WHERE si.sale_id = ? ORDER BY si.id
        """,
        (sale_id,),
    ).fetchall()
    data["items"] = []
    for item in items:
        d = row_to_dict(item)
        assert d is not None
        d["quantity"] = micro_to_units(int(d["quantity"]))
        d["unit_price"] = paise_to_rupees(int(d["unit_price"]))
        d["line_total"] = paise_to_rupees(int(d["line_total"]))
        data["items"].append(d)
    data["financials"] = _financials(conn, sale_id, status, lines)
    data["corrections"] = [row_to_dict(r) for r in conn.execute(
        "SELECT id, line_key, added, removed, created_at FROM sale_corrections WHERE sale_id = ? ORDER BY id",
        (sale_id,),
    )]
    data["returns"] = []
    for r in conn.execute("SELECT * FROM sale_returns WHERE sale_id = ? ORDER BY id", (sale_id,)):
        d = row_to_dict(r)
        assert d
        d["quantity"] = micro_to_units(int(d["quantity"]))
        d["unit_price"] = paise_to_rupees(int(d["unit_price"]))
        d["line_total"] = paise_to_rupees(int(d["line_total"]))
        d.pop("idempotency_hash", None)
        data["returns"].append(d)
    cancel = conn.execute("SELECT created_at, reversal_paise FROM sale_cancellations WHERE sale_id = ?", (sale_id,)).fetchone()
    data["cancellation"] = None
    if cancel:
        data["cancellation"] = {
            "created_at": cancel["created_at"],
            "reversal": paise_to_rupees(int(cancel["reversal_paise"])),
        }
    return data


def get_sale_detail(sale_id: int) -> dict[str, Any]:
    with atomic_connection() as conn:
        return sale_detail(conn, sale_id)


def list_sales(*, on_date: str | None = None, date_from: str | None = None, date_to: str | None = None, sale_id: int | None = None) -> list[dict[str, Any]]:
    with atomic_connection() as conn:
        sql = "SELECT id FROM sales WHERE 1=1"
        args: list[Any] = []
        if sale_id is not None:
            sql += " AND id = ?"
            args.append(sale_id)
        if on_date:
            sql += " AND transaction_date = ?"
            args.append(on_date)
        if date_from:
            sql += " AND transaction_date >= ?"
            args.append(date_from)
        if date_to:
            sql += " AND transaction_date <= ?"
            args.append(date_to)
        sql += " ORDER BY id DESC LIMIT 200"
        rows = conn.execute(sql, args).fetchall()
        return [sale_detail(conn, int(r["id"])) for r in rows]


def product_breakdown(conn: sqlite3.Connection, sale_ids: list[int]) -> list[dict[str, Any]]:
    """Net qty/amount per product from effective lines. Frozen return amounts. Skip cancelled/removed."""
    agg: dict[int, dict[str, Any]] = {}
    for sid in sale_ids:
        sale = conn.execute("SELECT status FROM sales WHERE id = ?", (sid,)).fetchone()
        if not sale or (sale["status"] or "open") == "cancelled":
            continue
        for ln in _lines_state(conn, sid):
            if ln["removed"] or not ln["product_id_int"]:
                continue
            pid = int(ln["product_id_int"])
            qty = int(ln["remaining_micro"])
            amt = int(ln["effective_line_gross_paise"]) - int(ln["returned_amount_paise"])
            if qty == 0 and amt == 0:
                continue
            slot = agg.setdefault(
                pid,
                {
                    "product_id": pid,
                    "name": ln["product_name"],
                    "unit": ln["unit"],
                    "quantity_micro": 0,
                    "amount_paise": 0,
                },
            )
            slot["quantity_micro"] += qty
            slot["amount_paise"] += amt
    rows = sorted(agg.values(), key=lambda r: (-r["amount_paise"], r["name"] or ""))
    return [
        {
            "product_id": r["product_id"],
            "name": r["name"],
            "unit": r["unit"],
            "quantity": micro_to_units(int(r["quantity_micro"])),
            "amount": paise_to_rupees(int(r["amount_paise"])),
            "amount_paise": int(r["amount_paise"]),
        }
        for r in rows
    ]


def sale_ids_for_scope(conn: sqlite3.Connection, *, day: str | None = None, start: str | None = None, end: str | None = None) -> list[int]:
    sql = "SELECT id FROM sales WHERE 1=1"
    args: list[Any] = []
    if day:
        sql += " AND transaction_date = ?"
        args.append(day)
    if start:
        sql += " AND transaction_date >= ?"
        args.append(start)
    if end:
        sql += " AND transaction_date <= ?"
        args.append(end)
    return [int(r["id"]) for r in conn.execute(sql, args).fetchall()]


def net_paise(conn: sqlite3.Connection, sale_id: int) -> int:
    sale = conn.execute("SELECT status FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if not sale:
        return 0
    lines = _lines_state(conn, sale_id)
    return int(_financials(conn, sale_id, sale["status"] or "open", lines)["net_recorded_paise"])


def last_open_sale_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(
        "SELECT id FROM sales WHERE status = 'open' OR status IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def find_open_sales_with_product(conn: sqlite3.Connection, product_id: int, limit: int = 8) -> list[int]:
    hits: list[int] = []
    rows = conn.execute(
        "SELECT id FROM sales WHERE status = 'open' OR status IS NULL ORDER BY id DESC LIMIT 40"
    ).fetchall()
    for r in rows:
        sid = int(r["id"])
        for ln in _lines_state(conn, sid):
            if ln["product_id"] == product_id and ln["remaining_micro"] > 0:
                hits.append(sid)
                break
        if len(hits) >= limit:
            break
    return hits


def _require_open(conn: sqlite3.Connection, sale_id: int) -> sqlite3.Row:
    sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale is None:
        raise ApiError("Sale not found", 404, "not_found")
    if (sale["status"] or "open") == "cancelled":
        raise ApiError("Sale is cancelled", 409, "conflict")
    return sale


def correct_line(
    sale_id: int,
    *,
    line_key: str | None,
    product_id: int | None,
    quantity: Any | None,
    unit_price: Any | None,
    add_line: bool = False,
    remove_line: bool = False,
    idempotency_key: str | None,
    conn: sqlite3.Connection | None = None,
) -> tuple[dict[str, Any], bool]:
    payload = {
        "sale_id": sale_id,
        "line_key": line_key,
        "product_id": product_id,
        "quantity": quantity,
        "unit_price": unit_price,
        "add_line": add_line,
        "remove_line": remove_line,
    }
    digest = _digest(payload)

    def _run(c: sqlite3.Connection) -> tuple[dict[str, Any], bool]:
        replay = _replay(c, "sale_corrections", idempotency_key, digest)
        if replay:
            return replay, True
        _require_open(c, sale_id)
        now = now_business().isoformat()
        if add_line:
            if product_id is None or quantity is None or unit_price is None:
                raise ApiError("New line needs product, quantity and unit_price", 400, "missing_field")
            qty_m = units_to_micro(quantity, "quantity")
            if qty_m <= 0:
                raise ApiError("quantity must be greater than 0", 400, "invalid_value")
            price_p = rupees_to_paise(unit_price, "unit_price")
            total_p = line_paise(qty_m, price_p)
            key = str(uuid.uuid4())
            c.execute(
                """
                INSERT INTO sale_lines (sale_id, line_key, origin_sale_item_id, added, removed, created_at)
                VALUES (?, ?, NULL, 1, 0, ?)
                """,
                (sale_id, key, now),
            )
            apply_stock_change(
                c,
                int(product_id),
                movement_type="sale_correction",
                delta_micro=-qty_m,
                unit_cost_paise=None,
                notes=f"sale_correction:{sale_id}",
                ref_sale_id=sale_id,
                ref_line_key=key,
                ref_kind="correction",
            )
            c.execute(
                """
                INSERT INTO sale_corrections (
                    sale_id, line_key, added, removed, product_id, quantity, unit_price, line_total,
                    before_json, after_json, idempotency_key, idempotency_hash, created_at
                ) VALUES (?, ?, 1, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sale_id,
                    key,
                    int(product_id),
                    qty_m,
                    price_p,
                    total_p,
                    json.dumps({"remaining_micro": 0}),
                    json.dumps({"product_id": product_id, "quantity_micro": qty_m}),
                    idempotency_key,
                    digest,
                    now,
                ),
            )
            return sale_detail(c, sale_id), False

        if not line_key:
            raise ApiError("line_key is required", 400, "missing_field")
        states = {x["line_key"]: x for x in _lines_state(c, sale_id)}
        cur = states.get(line_key)
        if not cur:
            raise ApiError("Sale line not found", 404, "not_found")
        old_pid = int(cur["product_id_int"])
        old_eff = int(cur["effective_qty_micro"])
        ret = int(cur["returned_qty_micro"])
        old_rem = old_eff - ret
        new_pid = int(product_id) if product_id is not None else old_pid
        if remove_line:
            if ret:
                raise ApiError("Cannot remove a line with returns", 409, "conflict")
            new_eff = 0
        else:
            new_eff = units_to_micro(quantity, "quantity") if quantity is not None else old_eff
        if new_eff < ret:
            raise ApiError("Quantity cannot be below already returned quantity", 409, "invalid_value")
        new_rem = new_eff - ret
        new_price = rupees_to_paise(unit_price, "unit_price") if unit_price is not None else int(cur["unit_price_paise"])
        new_total = line_paise(new_eff, new_price) if new_eff else 0
        if new_pid != old_pid:
            if ret:
                raise ApiError("Cannot change product after a return on this line", 409, "conflict")
            apply_stock_change(
                c,
                old_pid,
                movement_type="sale_correction",
                delta_micro=old_rem,
                unit_cost_paise=None,
                notes=f"sale_correction:{sale_id}",
                ref_sale_id=sale_id,
                ref_line_key=line_key,
                ref_kind="correction",
            )
            if new_eff > 0:
                apply_stock_change(
                    c,
                    new_pid,
                    movement_type="sale_correction",
                    delta_micro=-new_eff,
                    unit_cost_paise=None,
                    notes=f"sale_correction:{sale_id}",
                    ref_sale_id=sale_id,
                    ref_line_key=line_key,
                    ref_kind="correction",
                )
        else:
            delta = old_rem - new_rem
            if delta != 0:
                apply_stock_change(
                    c,
                    old_pid,
                    movement_type="sale_correction",
                    delta_micro=delta,
                    unit_cost_paise=None,
                    notes=f"sale_correction:{sale_id}",
                    ref_sale_id=sale_id,
                    ref_line_key=line_key,
                    ref_kind="correction",
                )
        if remove_line:
            c.execute("UPDATE sale_lines SET removed = 1 WHERE sale_id = ? AND line_key = ?", (sale_id, line_key))
        c.execute(
            """
            INSERT INTO sale_corrections (
                sale_id, line_key, added, removed, product_id, quantity, unit_price, line_total,
                before_json, after_json, idempotency_key, idempotency_hash, created_at
            ) VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sale_id,
                line_key,
                1 if remove_line else 0,
                new_pid,
                new_eff,
                new_price,
                new_total,
                json.dumps({"product_id": old_pid, "quantity_micro": old_eff, "remaining_micro": old_rem}),
                json.dumps({"product_id": new_pid, "quantity_micro": new_eff, "remaining_micro": new_rem}),
                idempotency_key,
                digest,
                now,
            ),
        )
        return sale_detail(c, sale_id), False

    if conn is not None:
        return _run(conn)
    with atomic_connection() as owned:
        return _run(owned)


def return_qty(
    sale_id: int,
    *,
    line_key: str,
    quantity: Any,
    idempotency_key: str | None,
    conn: sqlite3.Connection | None = None,
) -> tuple[dict[str, Any], bool]:
    qty_m = units_to_micro(quantity, "quantity")
    if qty_m <= 0:
        raise ApiError("quantity must be greater than 0", 400, "invalid_value")
    payload = {"sale_id": sale_id, "line_key": line_key, "quantity_micro": qty_m}
    digest = _digest(payload)

    def _run(c: sqlite3.Connection) -> tuple[dict[str, Any], bool]:
        replay = _replay(c, "sale_returns", idempotency_key, digest)
        if replay:
            return replay, True
        _require_open(c, sale_id)
        states = {x["line_key"]: x for x in _lines_state(c, sale_id)}
        cur = states.get(line_key)
        if not cur:
            raise ApiError("Sale line not found", 404, "not_found")
        remaining = int(cur["remaining_micro"])
        if qty_m > remaining:
            raise ApiError("Cannot return more than remaining quantity", 409, "invalid_value")
        price = int(cur["unit_price_paise"])
        total = line_paise(qty_m, price)
        now = now_business().isoformat()
        apply_stock_change(
            c,
            int(cur["product_id_int"]),
            movement_type="sale_return",
            delta_micro=qty_m,
            unit_cost_paise=None,
            notes=f"sale_return:{sale_id}",
            ref_sale_id=sale_id,
            ref_line_key=line_key,
            ref_kind="return",
        )
        try:
            c.execute(
                """
                INSERT INTO sale_returns (
                    sale_id, line_key, quantity, unit_price, line_total,
                    idempotency_key, idempotency_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (sale_id, line_key, qty_m, price, total, idempotency_key, digest, now),
            )
        except sqlite3.IntegrityError:
            again = _replay(c, "sale_returns", idempotency_key, digest)
            if again:
                return again, True
            raise
        return sale_detail(c, sale_id), False

    if conn is not None:
        return _run(conn)
    with atomic_connection() as owned:
        return _run(owned)


def cancel_sale(
    sale_id: int,
    *,
    idempotency_key: str | None,
    conn: sqlite3.Connection | None = None,
) -> tuple[dict[str, Any], bool]:
    payload = {"sale_id": sale_id, "op": "cancel"}
    digest = _digest(payload)

    def _run(c: sqlite3.Connection) -> tuple[dict[str, Any], bool]:
        replay = _replay(c, "sale_cancellations", idempotency_key, digest)
        if replay:
            return replay, True
        _require_open(c, sale_id)
        lines = _lines_state(c, sale_id)
        fin = _financials(c, sale_id, "open", lines)
        remaining_net = int(fin["net_recorded_paise"])
        now = now_business().isoformat()
        for ln in lines:
            rem = int(ln["remaining_micro"])
            if rem > 0 and ln["product_id_int"]:
                apply_stock_change(
                    c,
                    int(ln["product_id_int"]),
                    movement_type="sale_cancel",
                    delta_micro=rem,
                    unit_cost_paise=None,
                    notes=f"sale_cancel:{sale_id}",
                    ref_sale_id=sale_id,
                    ref_line_key=ln["line_key"],
                    ref_kind="cancel",
                )
        c.execute(
            """
            INSERT INTO sale_cancellations (sale_id, reversal_paise, idempotency_key, idempotency_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sale_id, remaining_net, idempotency_key, digest, now),
        )
        c.execute(
            "UPDATE sales SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
            (now, sale_id),
        )
        return sale_detail(c, sale_id), False

    if conn is not None:
        return _run(conn)
    with atomic_connection() as owned:
        return _run(owned)
