from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from db import atomic_connection
from errors import ApiError
from money import micro_to_units, paise_to_rupees
from timeutil import business_date_str, now_business, parse_business_date
from services import stock as stock_service


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


def yesterday_date() -> str:
    return (now_business().date() - timedelta(days=1)).isoformat()


def sales_yesterday() -> dict[str, Any]:
    return sales_for_date(yesterday_date())


def _range_totals(conn, start: str, end: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(total_amount), 0) AS total, COUNT(*) AS transactions
        FROM sales
        WHERE transaction_date >= ? AND transaction_date <= ?
        """,
        (start, end),
    ).fetchone()
    return {
        "total_amount": paise_to_rupees(int(row["total"])),
        "transactions": int(row["transactions"]),
    }


def _inclusive_days(start: str, end: str) -> list[str]:
    cur = date.fromisoformat(start)
    last = date.fromisoformat(end)
    days: list[str] = []
    while cur <= last:
        days.append(cur.isoformat())
        cur += timedelta(days=1)
    return days


def sales_trend(start: str, end: str) -> list[dict[str, Any]]:
    with atomic_connection(immediate=False) as conn:
        rows = conn.execute(
            """
            SELECT transaction_date AS day,
                   COALESCE(SUM(total_amount), 0) AS total,
                   COUNT(*) AS transactions
            FROM sales
            WHERE transaction_date >= ? AND transaction_date <= ?
            GROUP BY transaction_date
            ORDER BY transaction_date
            """,
            (start, end),
        ).fetchall()
        by_day = {
            r["day"]: {
                "date": r["day"],
                "total_amount": paise_to_rupees(int(r["total"])),
                "transactions": int(r["transactions"]),
            }
            for r in rows
        }
        return [
            by_day.get(day, {"date": day, "total_amount": 0, "transactions": 0})
            for day in _inclusive_days(start, end)
        ]


def product_sales_range(start: str, end: str) -> list[dict[str, Any]]:
    with atomic_connection(immediate=False) as conn:
        rows = conn.execute(
            """
            SELECT p.id AS product_id, p.name, p.unit,
                   COALESCE(SUM(si.quantity), 0) AS quantity,
                   COALESCE(SUM(si.line_total), 0) AS amount
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            JOIN products p ON p.id = si.product_id
            WHERE s.transaction_date >= ? AND s.transaction_date <= ?
            GROUP BY p.id, p.name, p.unit
            ORDER BY amount DESC, p.name COLLATE NOCASE
            """,
            (start, end),
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


def dashboard(start: str | None, end: str | None) -> dict[str, Any]:
    today = business_date_str()
    yest = yesterday_date()
    start = parse_business_date(start) if start else (now_business().date() - timedelta(days=6)).isoformat()
    end = parse_business_date(end) if end else today
    if start > end:
        raise ApiError("from date must be on or before to date", 400, "invalid_value")

    today_block = sales_for_date(today)
    yest_block = sales_for_date(yest)
    with atomic_connection(immediate=False) as conn:
        period = _range_totals(conn, start, end)
    trend = sales_trend(start, end)
    by_product = product_sales_range(start, end)
    stock = stock_service.list_stock()
    low = stock_service.list_stock(low_only=True)
    return {
        "timezone": "Asia/Kolkata",
        "cash_note": "Amounts are recorded sales, not cash received.",
        "profit_note": "Profit is not shown. Purchase cost is often unknown.",
        "today": today_block,
        "yesterday": yest_block,
        "period": {"from": start, "to": end, **period},
        "trend": trend,
        "best_sellers": by_product[:5],
        "by_product": by_product,
        "inventory": stock,
        "low_stock": low,
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
