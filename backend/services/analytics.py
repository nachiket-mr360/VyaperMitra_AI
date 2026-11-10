from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from db import atomic_connection
from errors import ApiError
from money import micro_to_units, paise_to_rupees
from timeutil import business_date_str, now_business, parse_business_date
from services import stock as stock_service


def _net_totals(conn, *, day: str | None = None, start: str | None = None, end: str | None = None) -> tuple[int, int, int]:
    from services.sale_lifecycle import net_paise

    sql = "SELECT id, COALESCE(status, 'open') AS status FROM sales WHERE 1=1"
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
    rows = conn.execute(sql, args).fetchall()
    active = [r for r in rows if (r["status"] or "open") != "cancelled"]
    cancelled = len(rows) - len(active)
    total = sum(net_paise(conn, int(r["id"])) for r in rows)
    return total, len(active), cancelled


def sales_for_date(day: str) -> dict[str, Any]:
    with atomic_connection() as conn:
        from services.sale_lifecycle import product_breakdown, sale_ids_for_scope

        net, ntx, ncan = _net_totals(conn, day=day)
        by_product = product_breakdown(conn, sale_ids_for_scope(conn, day=day))
        return {
            "date": day,
            "timezone": "Asia/Kolkata",
            "total_amount": paise_to_rupees(int(net)),
            "transactions": int(ntx),
            "cancelled_bills": int(ncan),
            "by_product": [{k: v for k, v in r.items() if k != "amount_paise"} for r in by_product],
        }


def sales_today() -> dict[str, Any]:
    return sales_for_date(business_date_str())


def sales_summary() -> dict[str, Any]:
    with atomic_connection() as conn:
        net, ntx, ncan = _net_totals(conn)
        return {
            "total_amount": paise_to_rupees(net),
            "transactions": ntx,
            "cancelled_bills": ncan,
            "cash_received": None,
            "cash_refunded": None,
        }


def yesterday_date() -> str:
    return (now_business().date() - timedelta(days=1)).isoformat()


def sales_yesterday() -> dict[str, Any]:
    return sales_for_date(yesterday_date())


def _range_totals(conn, start: str, end: str) -> dict[str, Any]:
    net, ntx, ncan = _net_totals(conn, start=start, end=end)
    return {
        "total_amount": paise_to_rupees(net),
        "transactions": ntx,
        "cancelled_bills": ncan,
        "cash_received": None,
        "cash_refunded": None,
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
        return [
            {
                "date": day,
                "total_amount": paise_to_rupees(net),
                "transactions": ntx,
                "cancelled_bills": ncan,
            }
            for day in _inclusive_days(start, end)
            for net, ntx, ncan in [_net_totals(conn, day=day)]
        ]


def product_sales_range(start: str, end: str) -> list[dict[str, Any]]:
    with atomic_connection(immediate=False) as conn:
        from services.sale_lifecycle import product_breakdown, sale_ids_for_scope

        rows = product_breakdown(conn, sale_ids_for_scope(conn, start=start, end=end))
        return [{k: v for k, v in r.items() if k != "amount_paise"} for r in rows]


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
        from services.sale_lifecycle import product_breakdown, sale_ids_for_scope

        rows = product_breakdown(conn, sale_ids_for_scope(conn))
        return [{k: v for k, v in r.items() if k != "amount_paise"} for r in rows]


def _period_bounds(period: str, today: date) -> tuple[str, str]:
    end = today.isoformat()
    if period == "yesterday":
        d = (today - timedelta(days=1)).isoformat()
        return d, d
    if period == "week":
        return (today - timedelta(days=6)).isoformat(), end
    if period == "month":
        return today.replace(day=1).isoformat(), end
    if period == "all":
        return "1970-01-01", end
    if period in {"days_30", "last_30"}:
        return (today - timedelta(days=29)).isoformat(), end
    return end, end


def _normalize_topic(topic: str) -> str:
    topic = (topic or "sales_summary").strip().lower()
    return {
        "sales": "sales_summary",
        "best_sellers": "best_selling_product",
        "best_selling": "best_selling_product",
        "product_wise": "product_breakdown",
    }.get(topic, topic)


def _sales_block(period: str) -> dict[str, Any]:
    if period == "yesterday":
        return {"period": "yesterday", **sales_yesterday()}
    if period == "all":
        return {"period": "all", **sales_summary(), "by_product": product_sales()}
    if period in {"week", "month", "days_30", "last_30"}:
        today = now_business().date()
        start, end = _period_bounds(period, today)
        dash = dashboard(start, end)
        return {
            "period": {"from": start, "to": end},
            "total_amount": dash["period"]["total_amount"],
            "transactions": dash["period"]["transactions"],
            "cancelled_bills": dash["period"].get("cancelled_bills"),
            "by_product": dash["by_product"],
        }
    return {"period": "today", **sales_today()}


def voice_query(topic: str, period: str | None, product: str | None = None) -> dict[str, Any]:
    """Read-only figures from existing analytics/stock queries. Never invent totals."""
    today = now_business().date()
    topic = _normalize_topic(topic)
    period = (period or "today").strip().lower()
    if topic == "unsupported":
        return {"topic": topic, "error": "unsupported_analytics"}
    if topic == "low_stock":
        return {"topic": topic, "low_stock": stock_service.list_stock(low_only=True)}
    if topic == "stock":
        return {"topic": topic, "inventory": stock_service.list_stock()}
    if topic == "unknown_stock":
        inv = stock_service.list_stock()
        unknown = [p for p in inv if not p.get("stock_known", True)]
        return {"topic": topic, "inventory": unknown}
    if topic == "slow_moving":
        start, end = _period_bounds(period if period not in {None, "today"} else "week", today)
        sold = {r["product_id"] for r in product_sales_range(start, end) if float(r.get("quantity") or 0) > 0}
        inv = stock_service.list_stock()
        slow = [
            p
            for p in inv
            if p.get("stock_known") and p.get("id") not in sold
        ]
        return {
            "topic": topic,
            "period": {"from": start, "to": end},
            "slow_moving": slow,
            "note": "Products with counted stock and no recorded sales in this period. Not a demand forecast.",
        }
    if topic == "period_compare":
        return compare_periods(period if period in {"week", "month"} else "week")
    if topic == "sales_trend":
        start, end = _period_bounds(period if period in {"week", "month", "days_30", "last_30"} else "week", today)
        trend = sales_trend(start, end)
        totals = _range_totals_pair(start, end)
        return {
            "topic": topic,
            "period": {"from": start, "to": end},
            "trend": trend,
            "total_amount": totals["total_amount"],
            "transactions": totals["transactions"],
            "cancelled_bills": totals.get("cancelled_bills"),
        }
    if topic == "overview":
        dash = dashboard(None, None)
        return {
            "topic": topic,
            "today": dash["today"],
            "yesterday": dash["yesterday"],
            "period": dash["period"],
            "trend": dash["trend"],
            "best_sellers": dash["best_sellers"],
            "low_stock": dash["low_stock"],
            "cash_note": dash["cash_note"],
            "profit_note": dash["profit_note"],
            "total_amount": dash["period"]["total_amount"],
            "transactions": dash["period"]["transactions"],
            "cancelled_bills": dash["period"].get("cancelled_bills"),
        }

    block = _sales_block(period)
    by_product = list(block.get("by_product") or [])
    if topic == "best_selling_product":
        start, end = _period_bounds(period, today)
        rows = product_sales_range(start, end)
        best = max(rows, key=lambda r: (float(r["quantity"]), float(r["amount"])), default=None)
        return {
            "topic": topic,
            "period": {"from": start, "to": end},
            "metric": "quantity",
            "best_sellers": rows[:5],
            "best_selling": best,
        }
    if topic == "product_sales":
        name = (product or "").strip().lower()
        matched = [r for r in by_product if name and name in str(r.get("name") or "").lower()]
        return {
            "topic": topic,
            "period": block.get("period"),
            "product_query": product,
            "by_product": matched,
        }
    if topic == "product_breakdown":
        return {
            "topic": topic,
            "period": block.get("period"),
            "by_product": by_product,
        }
    if topic == "sales_summary_and_products":
        return {
            "topic": topic,
            "period": block.get("period"),
            "total_amount": block.get("total_amount", 0),
            "transactions": block.get("transactions", 0),
            "cancelled_bills": block.get("cancelled_bills"),
            "by_product": by_product,
        }
    # sales_summary
    out = {
        "topic": "sales_summary",
        "period": block.get("period"),
        "total_amount": block.get("total_amount", 0),
        "transactions": block.get("transactions", 0),
        "cancelled_bills": block.get("cancelled_bills"),
    }
    if "date" in block:
        out["date"] = block["date"]
    if period in {"week", "month", "days_30", "last_30"}:
        start, end = _period_bounds(period, today)
        out["trend"] = sales_trend(start, end)
        out["period"] = {
            "from": start,
            "to": end,
            "total_amount": out["total_amount"],
            "transactions": out["transactions"],
            "cancelled_bills": out.get("cancelled_bills"),
        }
    return out


def _range_totals_pair(start: str, end: str) -> dict[str, Any]:
    with atomic_connection(immediate=False) as conn:
        return _range_totals(conn, start, end)


def compare_periods(kind: str) -> dict[str, Any]:
    today = now_business().date()
    if kind == "month":
        cur_s = today.replace(day=1)
        cur_e = today
        prev_e = cur_s - timedelta(days=1)
        prev_s = prev_e.replace(day=1)
        label = "month"
    else:
        cur_s = today - timedelta(days=6)
        cur_e = today
        prev_e = cur_s - timedelta(days=1)
        prev_s = prev_e - timedelta(days=6)
        label = "week"
    current = {
        "from": cur_s.isoformat(),
        "to": cur_e.isoformat(),
        **_range_totals_pair(cur_s.isoformat(), cur_e.isoformat()),
    }
    previous = {
        "from": prev_s.isoformat(),
        "to": prev_e.isoformat(),
        **_range_totals_pair(prev_s.isoformat(), prev_e.isoformat()),
    }
    prev_amt = float(previous["total_amount"] or 0)
    cur_amt = float(current["total_amount"] or 0)
    delta = cur_amt - prev_amt
    pct = None
    if prev_amt != 0:
        pct = round((delta / prev_amt) * 100, 1)
    return {
        "topic": "period_compare",
        "compare": label,
        "current": current,
        "previous": previous,
        "delta_amount": delta,
        "percent_change": pct,
        "metric": "recorded_sales_amount",
        "note": "Recorded sales amounts, not cash received. No cause is inferred.",
    }

