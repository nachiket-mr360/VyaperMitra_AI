"""Resolve short analytics follow-ups from session context. Not an LLM."""

from __future__ import annotations

import re
from typing import Any

from validate import normalize_text


def parse_followup(transcript: str, ctx: dict[str, Any] | None) -> dict[str, Any] | None:
    if not ctx:
        return None
    last = ctx.get("last_analytics")
    if not last and ctx.get("last_product"):
        last = {
            "analytics_topic": "check_stock" if ctx.get("last_intent") == "check_stock" else "product_sales",
            "product": ctx.get("last_product"),
            "period": "today",
        }
    n = normalize_text(transcript or "")
    if not n:
        return None
    want_chart = bool(re.search(r"as a chart|show (it )?as (a )?chart|chart|ग्राफ|चार्ट", n))
    if last and want_chart and len(n.split()) <= 8:
        return {**last, "force_chart": True, "followup": True}
    if not last:
        if want_chart:
            return {"clarification": True, "message": "Which figures should I chart — today's sales, this week, or products?"}
        return None
    if last and re.search(
        r"how much.*(sell|sold)|how much did i|कितना बेचा|कितनी बिकी|ಎಷ್ಟು ಮಾರಾಟ|किती विकली",
        n,
    ):
        topic = last.get("analytics_topic") or "product_sales"
        if topic in {"check_stock", "stock", "low_stock"}:
            topic = "product_sales"
        return {
            **last,
            "analytics_topic": topic,
            "product": last.get("product") or ctx.get("last_product"),
            "followup": True,
        }
    if last and re.search(r"last month|पिछले महीने|ಕಳೆದ ತಿಂಗಳು|मागच्या महिन्या", n) and len(n.split()) <= 10:
        return {
            **last,
            "period": "month",
            "product": last.get("product") or ctx.get("last_product"),
            "followup": True,
        }
    if last and re.fullmatch(r"(it|that|that product|same item|the same|वही|ಅದೇ|तेच)\??", n):
        return {**last, "followup": True}
    if re.search(r"what about yesterday|and yesterday|yesterday\??$|कल का|ನಿನ್ನೆ", n) and len(n.split()) <= 8:
        return {**last, "period": "yesterday", "followup": True, "force_chart": want_chart}
    if re.search(r"what about today|and today", n) and len(n.split()) <= 8:
        return {**last, "period": "today", "followup": True}
    if re.search(r"compare.*(last )?week|with last week|पिछले हफ्ते", n):
        return {
            "analytics_topic": "period_compare",
            "period": "week",
            "product": last.get("product"),
            "followup": True,
        }
    if re.search(r"compare.*(last )?month|with last month", n):
        return {"analytics_topic": "period_compare", "period": "month", "followup": True}
    if re.search(r"^what about ([a-zA-Z\u0900-\u097F]{2,40})\??$", n) or re.search(r"^and ([a-zA-Z]{2,40})\??$", n):
        m = re.search(r"(?:what about|and)\s+([a-zA-Z\u0900-\u097F]+)", n)
        if m:
            word = m.group(1)
            if word in {"yesterday", "today", "it", "that", "this"}:
                if word in {"it", "that", "this"} and not last.get("analytics_topic"):
                    return {"clarification": True, "message": "Do you mean sales, stock, or a product?"}
                return None
            topic = last.get("analytics_topic") or "check_stock"
            if topic in {"check_stock", "stock", "low_stock"}:
                return {"intent": "product_follow", "product": word}
            return {
                "analytics_topic": "product_sales",
                "period": last.get("period") or "today",
                "product": word,
                "followup": True,
            }
    if n in {"what about it", "and that", "the same"}:
        return {"clarification": True, "message": "Do you mean the same sales figures, another day, or another product?"}
    return None
