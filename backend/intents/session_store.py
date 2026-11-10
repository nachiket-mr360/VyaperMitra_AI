"""In-memory short-term voice context. No SQLite. Isolated per session_id."""

from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}
def _max_turns() -> int:
    try:
        from config import Config

        n = int(getattr(Config, "SESSION_CONTEXT_TURNS", 12))
        return max(4, min(40, n))
    except Exception:
        return 12


MAX_TURNS = 12
TTL_SECONDS = 30 * 60
MAX_SESSIONS = 200


def reset() -> None:
    with _LOCK:
        _SESSIONS.clear()


def _purge_locked(now: float) -> None:
    dead = [k for k, v in _SESSIONS.items() if now - v["updated"] > TTL_SECONDS]
    for k in dead:
        _SESSIONS.pop(k, None)
    if len(_SESSIONS) > MAX_SESSIONS:
        oldest = sorted(_SESSIONS.items(), key=lambda kv: kv[1]["updated"])
        for k, _ in oldest[: len(_SESSIONS) - MAX_SESSIONS]:
            _SESSIONS.pop(k, None)


def _blank() -> dict[str, Any]:
    return {
        "turns": [],
        "pending_id": None,
        "last_product": None,
        "last_sale_id": None,
        "last_sale_fp": None,
        "last_sale_ts": 0.0,
        "last_sale_result": None,
        "last_intent": None,
        "skip_extract": False,
        "forget_all_pending": False,
        "last_analytics": None,
        "clarification_slot": None,
        "last_reply_language": None,
        "updated": time.time(),
    }


def get(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    with _LOCK:
        _purge_locked(time.time())
        row = _SESSIONS.get(session_id)
        return dict(row) if row else None


def ensure(session_id: str) -> dict[str, Any]:
    with _LOCK:
        now = time.time()
        _purge_locked(now)
        row = _SESSIONS.get(session_id)
        if row is None:
            row = _blank()
            _SESSIONS[session_id] = row
        row["updated"] = now
        return row


def set_pending(session_id: str | None, pending_id: str | None) -> None:
    if not session_id:
        return
    row = ensure(session_id)
    row["pending_id"] = pending_id


def ops_period(res: dict[str, Any]) -> str | None:
    p = res.get("period")
    if isinstance(p, str):
        return p
    if isinstance(p, dict):
        return None
    return None


def history(session_id: str | None) -> list[dict[str, str]]:
    ctx = get(session_id)
    if not ctx:
        return []
    return list(ctx.get("turns") or [])


def remember(session_id: str | None, user_text: str, assistant_text: str, result: dict[str, Any]) -> None:
    if not session_id:
        return
    row = ensure(session_id)
    turns: list[dict[str, str]] = row["turns"]
    turns.append({"role": "user", "text": user_text})
    turns.append({"role": "assistant", "text": assistant_text})
    overflow = len(turns) - _max_turns() * 2
    if overflow > 0:
        row["turns"] = turns[overflow:]
    else:
        row["turns"] = turns
    row["last_intent"] = result.get("intent")
    rl = result.get("reply_language")
    if rl in {"en", "hi", "kn", "mr"}:
        row["last_reply_language"] = rl
    product = None
    res = result.get("result")
    if isinstance(res, dict):
        product = res.get("name") or res.get("product_query")
    product = product or result.get("product_query")
    if isinstance(result.get("product"), dict):
        product = result["product"].get("name") or product
    if product:
        row["last_product"] = product
    sale_obj = None
    if isinstance(res, dict) and isinstance(res.get("sale"), dict):
        sale_obj = res["sale"]
    if sale_obj and sale_obj.get("id") is not None:
        row["last_sale_id"] = int(sale_obj["id"])
        row["last_sale_result"] = sale_obj
    if result.get("intent") == "check_analytics" and isinstance(result.get("result"), dict):
        res = result["result"]
        row["last_analytics"] = {
            "analytics_topic": res.get("topic") or "sales_summary",
            "period": ops_period(res),
            "product": res.get("product_query") or product,
        }
    pending = result.get("pending_id")
    if result.get("needs_confirmation") and pending:
        row["pending_id"] = pending
    elif result.get("intent") in {"confirmation", "cancellation"}:
        row["pending_id"] = None
    elif result.get("executed") and not result.get("needs_confirmation"):
        if result.get("intent") not in {"check_stock", "check_analytics", "general_conversation", "general_question", "business_advice"}:
            row["pending_id"] = row.get("pending_id")
