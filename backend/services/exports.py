"""CSV builders. No secrets. Integer money already converted on service rows."""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Iterable

from services import analytics as analytics_service
from services import products as product_service
from services import sales as sales_service
from timeutil import business_date_str, parse_business_date


def _safe_name(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", part)[:80] or "export"


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + text
    return text


def csv_bytes(headers: list[str], rows: Iterable[list[Any]]) -> bytes:
    buf = io.StringIO(newline="")
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_cell(c) for c in row])
    return buf.getvalue().encode("utf-8")


def sales_csv(*, on_date: str | None, date_from: str | None, date_to: str | None) -> tuple[bytes, str]:
    if on_date:
        on_date = parse_business_date(on_date)
    if date_from:
        date_from = parse_business_date(date_from)
    if date_to:
        date_to = parse_business_date(date_to)
    sales = sales_service.list_sales(on_date=on_date, date_from=date_from, date_to=date_to)
    headers = [
        "sale_id",
        "transaction_date",
        "status",
        "net_recorded_inr",
        "original_recorded_inr",
        "product",
        "unit",
        "quantity",
        "line_total_inr",
    ]
    rows: list[list[Any]] = []
    for sale in sales:
        fin = sale.get("financials") or {}
        lines = sale.get("lines") or sale.get("items") or []
        if not lines:
            rows.append(
                [
                    sale.get("id"),
                    sale.get("transaction_date"),
                    sale.get("status") or "open",
                    fin.get("net_recorded", sale.get("total_amount")),
                    fin.get("original_recorded"),
                    "",
                    "",
                    "",
                    "",
                ]
            )
            continue
        for line in lines:
            name = line.get("product_name") or line.get("name") or ""
            qty = line.get("effective_quantity", line.get("quantity"))
            total = line.get("line_total")
            rows.append(
                [
                    sale.get("id"),
                    sale.get("transaction_date"),
                    sale.get("status") or "open",
                    fin.get("net_recorded", sale.get("total_amount")),
                    fin.get("original_recorded"),
                    name,
                    line.get("unit") or "",
                    qty,
                    total,
                ]
            )
    stamp = date_from or on_date or "all"
    end = date_to or on_date or business_date_str()
    fname = f"sales_{_safe_name(stamp)}_to_{_safe_name(end)}.csv"
    return csv_bytes(headers, rows), fname


def inventory_csv() -> tuple[bytes, str]:
    products = product_service.list_products()
    headers = [
        "product_id",
        "name",
        "unit",
        "current_stock",
        "stock_known",
        "low_stock_threshold",
        "low_stock",
        "active",
    ]
    rows = []
    for p in products:
        rows.append(
            [
                p.get("id"),
                p.get("name"),
                p.get("unit"),
                p.get("current_stock") if p.get("stock_known") is not False else "",
                bool(p.get("stock_known", True)),
                p.get("low_stock_threshold"),
                bool(p.get("low_stock")),
                bool(p.get("active", True)),
            ]
        )
    return csv_bytes(headers, rows), "inventory.csv"


def analytics_csv(*, date_from: str | None, date_to: str | None) -> tuple[bytes, str]:
    dash = analytics_service.dashboard(date_from, date_to)
    period = dash.get("period") or {}
    headers = [
        "section",
        "date",
        "product",
        "unit",
        "quantity",
        "recorded_sales_inr",
        "transactions",
        "note",
    ]
    rows: list[list[Any]] = []
    note = "Recorded sales, not cash received. Profit is not included."
    today = dash.get("today") or {}
    rows.append(
        [
            "today",
            today.get("date"),
            "",
            "",
            "",
            today.get("total_amount"),
            today.get("transactions"),
            note,
        ]
    )
    rows.append(
        [
            "period",
            f"{period.get('from')}_{period.get('to')}",
            "",
            "",
            "",
            period.get("total_amount"),
            period.get("transactions"),
            note,
        ]
    )
    for t in dash.get("trend") or []:
        rows.append(["trend", t.get("date"), "", "", "", t.get("total_amount"), t.get("transactions"), note])
    for p in dash.get("by_product") or []:
        rows.append(
            [
                "by_product",
                f"{period.get('from')}_{period.get('to')}",
                p.get("name"),
                p.get("unit"),
                p.get("quantity"),
                p.get("amount"),
                "",
                note,
            ]
        )
    fname = f"analytics_{_safe_name(str(period.get('from') or 'from'))}_to_{_safe_name(str(period.get('to') or 'to'))}.csv"
    return csv_bytes(headers, rows), fname
