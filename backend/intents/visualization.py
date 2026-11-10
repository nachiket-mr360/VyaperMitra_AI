"""Flask-built chart payloads. Never from Gemini. No HTML/JS."""

from __future__ import annotations

from typing import Any

ALLOWED_TYPES = frozenset({"line", "bar", "hbar", "area", "comparison"})
ALLOWED_METRICS = frozenset(
    {
        "recorded_sales_amount",
        "sales_quantity",
        "transaction_count",
        "stock_quantity",
    }
)
CASH_NOTE = "Amounts are recorded sales, not cash received."
PROFIT_NOTE = "Profit is not shown. Purchase cost is often unknown."


def _num(v: Any) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n


def validate_visualization(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    ctype = raw.get("type")
    if ctype not in ALLOWED_TYPES:
        return None
    title = str(raw.get("title") or "").strip()[:120]
    if not title:
        return None
    metric = raw.get("metric")
    if metric not in ALLOWED_METRICS:
        return None
    points = raw.get("points")
    if not isinstance(points, list) or not points:
        return None
    clean = []
    for p in points[:31]:
        if not isinstance(p, dict):
            return None
        label = str(p.get("label") or "").strip()[:80]
        val = _num(p.get("value"))
        if not label or val is None:
            return None
        item: dict[str, Any] = {"label": label, "value": val}
        if p.get("value2") is not None:
            v2 = _num(p.get("value2"))
            if v2 is None:
                return None
            item["value2"] = v2
        clean.append(item)
    if not clean:
        return None
    rng = raw.get("date_range") if isinstance(raw.get("date_range"), dict) else {}
    dash = raw.get("dashboard") if isinstance(raw.get("dashboard"), dict) else {}
    kpis = []
    if isinstance(raw.get("kpis"), list):
        for k in raw["kpis"][:6]:
            if not isinstance(k, dict):
                continue
            lab = str(k.get("label") or "").strip()[:40]
            val = _num(k.get("value"))
            if lab and val is not None:
                kpis.append({"label": lab, "value": val})
    return {
        "type": ctype,
        "title": title,
        "subtitle": str(raw.get("subtitle") or "")[:200],
        "x_key": "label",
        "y_key": "value",
        "y_label": str(raw.get("y_label") or "Recorded sales (₹)")[:80],
        "unit": str(raw.get("unit") or "INR")[:20],
        "metric": metric,
        "date_range": {"from": rng.get("from"), "to": rng.get("to")},
        "points": clean,
        "kpis": kpis,
        "notes": [CASH_NOTE],
        "dashboard": {
            "page": dash.get("page") if dash.get("page") in {"insights", "sales", "inventory", "dashboard"} else "insights",
            "from": dash.get("from") or rng.get("from"),
            "to": dash.get("to") or rng.get("to"),
        },
    }


def _trend_kpis(result: dict[str, Any]) -> list[dict[str, Any]]:
    """KPIs for the same window as trend points. Never invent a zero when the value is missing."""
    period = result.get("period") if isinstance(result.get("period"), dict) else {}
    amt = period["total_amount"] if "total_amount" in period else result.get("total_amount")
    tx = period["transactions"] if "transactions" in period else result.get("transactions")
    series_amt = 0.0
    series_tx = 0
    for row in result.get("trend") or []:
        if not isinstance(row, dict):
            continue
        n = _num(row.get("total_amount"))
        if n is not None:
            series_amt += n
        series_tx += int(row.get("transactions") or 0)
    if amt is None:
        amt = series_amt
    else:
        amt_n = _num(amt)
        amt = series_amt if amt_n is None else amt_n
        if amt == 0 and series_amt != 0:
            amt = series_amt
    if tx is None:
        tx = series_tx
    else:
        try:
            tx = int(tx)
        except (TypeError, ValueError):
            tx = series_tx
        if tx == 0 and series_tx != 0:
            tx = series_tx
    kpis: list[dict[str, Any]] = []
    if amt is not None:
        kpis.append({"label": "Recorded sales", "value": amt})
    if tx is not None:
        kpis.append({"label": "Bills", "value": tx})
    ncan = period.get("cancelled_bills")
    if ncan is None:
        ncan = result.get("cancelled_bills")
    if ncan:
        kpis.append({"label": "Cancelled bills", "value": int(ncan)})
    return kpis


def from_analytics_result(result: dict[str, Any] | None, *, force: bool = False) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    topic = result.get("topic")
    if topic == "unsupported":
        return None
    if result.get("trend") and topic in {"sales_trend", "overview", "sales_summary"}:
        trend = result.get("trend") or []
        pts = [{"label": r.get("date"), "value": r.get("total_amount")} for r in trend]
        raw = {
            "type": "area" if topic == "sales_trend" else "line",
            "title": "Sales trend",
            "subtitle": "Recorded sales by day (not cash received)",
            "metric": "recorded_sales_amount",
            "y_label": "Recorded sales (₹)",
            "points": pts,
            "date_range": result.get("period") if isinstance(result.get("period"), dict) else {},
            "dashboard": {"page": "insights"},
            "kpis": _trend_kpis(result),
        }
        return validate_visualization(raw)
    if topic == "period_compare":
        cur = result.get("current") or {}
        prev = result.get("previous") or {}
        raw = {
            "type": "comparison",
            "title": "Period comparison",
            "subtitle": result.get("note") or CASH_NOTE,
            "metric": "recorded_sales_amount",
            "points": [
                {"label": "Previous", "value": prev.get("total_amount") or 0},
                {"label": "Current", "value": cur.get("total_amount") or 0},
            ],
            "date_range": {"from": prev.get("from"), "to": cur.get("to")},
            "dashboard": {"page": "insights", "from": cur.get("from"), "to": cur.get("to")},
        }
        return validate_visualization(raw)
    if topic in {"best_selling_product", "product_breakdown", "sales_summary_and_products"}:
        rows = result.get("best_sellers") or result.get("by_product") or []
        if result.get("best_selling") and not rows:
            rows = [result["best_selling"]]
        pts = [{"label": r.get("name"), "value": r.get("amount")} for r in rows[:8]]
        if not any(_num(p.get("value")) not in (None, 0) for p in pts) and not force:
            return None
        raw = {
            "type": "hbar",
            "title": "Product recorded sales",
            "subtitle": "By recorded amount, not profit",
            "metric": "recorded_sales_amount",
            "points": pts,
            "date_range": result.get("period") if isinstance(result.get("period"), dict) else {},
            "dashboard": {"page": "sales"},
        }
        return validate_visualization(raw)
    if topic == "product_sales":
        rows = result.get("by_product") or []
        pts = [{"label": r.get("name"), "value": r.get("amount")} for r in rows]
        return validate_visualization(
            {
                "type": "bar",
                "title": "Product sales",
                "subtitle": "Recorded amount",
                "metric": "recorded_sales_amount",
                "points": pts,
                "dashboard": {"page": "sales"},
            }
        )
    if topic == "low_stock":
        rows = result.get("low_stock") or []
        pts = [
            {"label": r.get("name"), "value": r.get("current_stock")}
            for r in rows
            if r.get("stock_known", True)
        ]
        return validate_visualization(
            {
                "type": "hbar",
                "title": "Low stock",
                "subtitle": "Counted quantity remaining",
                "metric": "stock_quantity",
                "y_label": "Stock",
                "unit": "qty",
                "points": pts,
                "dashboard": {"page": "inventory"},
            }
        )
    if topic == "sales_summary" and force:
        amt = result.get("total_amount")
        raw = {
            "type": "bar",
            "title": "Recorded sales",
            "subtitle": CASH_NOTE,
            "metric": "recorded_sales_amount",
            "points": [{"label": str(result.get("date") or result.get("period") or "period"), "value": amt}],
            "dashboard": {"page": "insights"},
        }
        return validate_visualization(raw)
    if topic == "sales_summary" and isinstance(result.get("period"), dict):
        # Multi-day summary: pull trend if present
        return None
    return None
