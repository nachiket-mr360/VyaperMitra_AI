"""Validate Gemini JSON. Never invent fields. No database."""

from __future__ import annotations

from typing import Any

from llm.gemini import ALLOWED_INTENTS
from validate import ALLOWED_UNITS

ALLOWED_RECURRENCE = frozenset({"none", "daily", "weekly", "monthly"})
_RECURRENCE_NONE_ALIASES = frozenset({"once", "one-time", "onetime", "one_time", "one time"})
ALLOWED_TOPICS = frozenset(
    {
        "sales",
        "sales_summary",
        "product_breakdown",
        "sales_summary_and_products",
        "best_selling_product",
        "best_sellers",
        "product_sales",
        "low_stock",
        "stock",
        "unsupported",
        "sales_trend",
        "period_compare",
        "unknown_stock",
        "slow_moving",
        "overview",
    }
)
ALLOWED_PERIODS = frozenset({"today", "yesterday", "week", "month", "all", "days_30", "last_30"})


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    return n


def validate_llm_payload(raw: dict[str, Any]) -> dict[str, Any]:
    intent = str(raw.get("intent") or "unknown").strip()
    if intent not in ALLOWED_INTENTS:
        intent = "unknown"
    product = raw.get("product")
    if product is not None:
        product = str(product).strip() or None
    qty = _num(raw.get("quantity"))
    if qty is not None and qty <= 0:
        qty = None
    unit = raw.get("unit")
    if unit is not None:
        unit = str(unit).strip().lower()
        if unit in {"litre", "liter", "litres", "liters"}:
            unit = "l"
        if unit in {"gram", "grams", "gm"}:
            unit = "g"
        if unit in {"kilo", "kilos", "kilogram", "kilograms"}:
            unit = "kg"
        if unit not in ALLOWED_UNITS:
            unit = None
    amount = _num(raw.get("amount"))
    if amount is not None and amount < 0:
        amount = None
    missing = raw.get("missing_fields") or []
    if not isinstance(missing, list):
        missing = []
    missing = [str(m) for m in missing]
    clar = bool(raw.get("clarification_required"))
    conf = _num(raw.get("confidence"))
    if conf is None:
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    title = raw.get("title")
    title = str(title).strip() if title else None
    body = raw.get("body")
    body = str(body).strip() if body else None
    due_date = raw.get("due_date")
    due_date = str(due_date).strip() if due_date else None
    due_time = raw.get("due_time")
    due_time = str(due_time).strip() if due_time else None
    rec = raw.get("recurrence")
    rec = str(rec).strip().lower() if rec not in (None, "") else "none"
    rec = rec.replace("_", "-").replace(" ", "-")
    if rec in _RECURRENCE_NONE_ALIASES or rec == "none":
        rec = "none"
    elif rec not in ALLOWED_RECURRENCE:
        rec = "none"

    topic = raw.get("analytics_topic")
    topic = str(topic).strip().lower() if topic else None
    if topic not in ALLOWED_TOPICS:
        topic = None
    period = raw.get("period")
    period = str(period).strip().lower() if period else None
    if period not in ALLOWED_PERIODS:
        period = None
    if intent == "check_analytics":
        if not topic:
            topic = "sales"
        if topic in {
            "sales",
            "sales_summary",
            "product_breakdown",
            "sales_summary_and_products",
            "best_sellers",
            "best_selling_product",
            "product_sales",
        } and not period:
            period = "today"
    if intent in {"purchase_stock", "record_sale", "check_stock"} and not product:
        if "product" not in missing:
            missing.append("product")
        clar = True
    if intent in {"purchase_stock", "record_sale"} and qty is None:
        if "quantity" not in missing:
            missing.append("quantity")
        clar = True
    if intent in {"purchase_stock", "record_sale"} and unit is None:
        if "unit" not in missing:
            missing.append("unit")
        clar = True
    if intent == "purchase_stock":
        missing = [m for m in missing if m not in {"amount", "sale_amount"}]
    if intent == "record_sale" and amount is None:
        if "amount" not in missing:
            missing.append("amount")
        clar = True
    if intent == "create_reminder" and not title:
        if "title" not in missing:
            missing.append("title")
        clar = True
    if intent == "create_note" and not body:
        if "body" not in missing:
            missing.append("body")
        clar = True
    if conf < 0.45 and intent not in {
        "general_conversation",
        "general_question",
        "business_advice",
    }:
        clar = True
        intent = "unknown"
    if intent in {"general_conversation", "general_question", "business_advice"}:
        clar = False
        missing = []

    return {
        "intent": intent,
        "product": product,
        "quantity": qty,
        "unit": unit,
        "amount": amount,
        "title": title,
        "body": body,
        "due_date": due_date,
        "due_time": due_time,
        "recurrence": rec,
        "analytics_topic": topic,
        "period": period,
        "missing": missing,
        "clarification_required": clar,
        "confidence": conf,
        "language": raw.get("language"),
        "meta": raw.get("_meta") or {},
    }
