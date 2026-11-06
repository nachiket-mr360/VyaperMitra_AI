from __future__ import annotations

from typing import Any

from db import atomic_connection
from money import micro_to_units, paise_to_rupees
from timeutil import business_date_str


def sales_for_date(day: str) -> dict[str, Any]:
    with atomic_connection() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(total_amount), 0) AS total, COUNT(*) AS transactions
            FROM sales
            WHERE transaction_date = ?
            """,
            (day,),
        ).fetchone()
        items = conn.execute(
            """
            SELECT p.id AS product_id, p.name, p.unit,
                   SUM(si.quantity) AS quantity, SUM(si.line_total) AS amount
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            JOIN products p ON p.id = si.product_id
            WHERE s.transaction_date = ?
            GROUP BY p.id, p.name, p.unit
            ORDER BY amount DESC
            """,
            (day,),
        ).fetchall()
        return {
            "date": day,
            "timezone": "Asia/Kolkata",
            "total_amount": paise_to_rupees(int(row["total"])),
            "transactions": int(row["transactions"]),
            "by_product": [
                {
                    "product_id": r["product_id"],
                    "name": r["name"],
                    "unit": r["unit"],
                    "quantity": micro_to_units(int(r["quantity"])),
                    "amount": paise_to_rupees(int(r["amount"])),
                }
                for r in items
            ],
        }


def sales_today() -> dict[str, Any]:
    return sales_for_date(business_date_str())


def sales_summary() -> dict[str, Any]:
    with atomic_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) AS total, COUNT(*) AS transactions FROM sales"
        ).fetchone()
        return {
            "total_amount": paise_to_rupees(int(row["total"])),
            "transactions": int(row["transactions"]),
        }


def product_sales() -> list[dict[str, Any]]:
    with atomic_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.id AS product_id, p.name, p.unit,
                   COALESCE(SUM(si.quantity), 0) AS quantity,
                   COALESCE(SUM(si.line_total), 0) AS amount
            FROM products p
            LEFT JOIN sale_items si ON si.product_id = p.id
            GROUP BY p.id, p.name, p.unit
            ORDER BY amount DESC, p.name COLLATE NOCASE
            """
        ).fetchall()
        return [
            {
                "product_id": r["product_id"],
                "name": r["name"],
                "unit": r["unit"],
                "quantity": micro_to_units(int(r["quantity"])),
                "amount": paise_to_rupees(int(r["amount"])),
            }
            for r in rows
        ]
