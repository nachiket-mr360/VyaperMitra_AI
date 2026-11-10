"""Persistent personal and business memory. No sales/stock figures. Flask-owned SQLite only."""

from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from config import Config
from db import atomic_connection, get_connection
from errors import ApiError
from timeutil import now_business
from validate import normalize_text

Layer = Literal["personal", "business"]

PERSONAL_KEYS = frozenset(
    {
        "preferred_name",
        "preferred_language",
        "explanation_style",
        "communication_preference",
        "long_term_goal",
        "interest",
    }
)
BUSINESS_KEYS = frozenset(
    {
        "shop_name",
        "shop_type",
        "location",
        "preferred_supplier",
        "business_goal",
        "operating_instruction",
    }
)
_SECRET = re.compile(
    r"password|api[_ ]?key|secret|otp|cvv|aadhaar|credit card|debit card|\bpin\b",
    re.I,
)
_INJECT = re.compile(r"ignore (all )?(previous|prior) (instructions|rules)|system prompt", re.I)
_MAX_VALUE = 200


def shop_id_or(explicit: str | None = None) -> str:
    sid = (explicit or Config.SHOP_ID or "default").strip()
    if not sid or len(sid) > 80:
        raise ApiError("Invalid shop identity.", 400, "invalid_value")
    return sid


def _now() -> str:
    return now_business().isoformat()


def _table(layer: Layer) -> str:
    return "personal_memories" if layer == "personal" else "business_memories"


def _allowed(layer: Layer, key: str) -> bool:
    if layer == "personal":
        return key in PERSONAL_KEYS or key.startswith("interest:")
    return key in BUSINESS_KEYS or key.startswith("supplier:")


def sanitize_value(value: str) -> str:
    text = (value or "").strip()
    if not text or len(text) > _MAX_VALUE:
        raise ApiError("That memory is empty or too long.", 400, "invalid_value")
    if _SECRET.search(text):
        raise ApiError("I will not store passwords, keys, or payment secrets.", 400, "sensitive_memory")
    if _INJECT.search(text):
        raise ApiError("That text cannot be stored as a memory.", 400, "invalid_value")
    return text


def upsert(
    layer: Layer,
    key: str,
    value: str,
    *,
    shop_id: str | None = None,
    source: str = "user_stated",
) -> dict[str, Any]:
    sid = shop_id_or(shop_id)
    key = (key or "").strip()[:80]
    if not _allowed(layer, key):
        raise ApiError("Unsupported memory key.", 400, "invalid_value")
    value = sanitize_value(value)
    table = _table(layer)
    now = _now()
    with atomic_connection() as conn:
        existing = conn.execute(
            f"SELECT * FROM {table} WHERE shop_id = ? AND mem_key = ? AND status = 'active'",
            (sid, key),
        ).fetchone()
        if existing:
            if existing["value"] == value:
                return _row(existing, layer, duplicate=True)
            conn.execute(
                f"UPDATE {table} SET value = ?, source = ?, updated_at = ? WHERE id = ? AND shop_id = ?",
                (value, source, now, existing["id"], sid),
            )
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (existing["id"],)).fetchone()
            return _row(row, layer, updated=True)
        mid = str(uuid.uuid4())
        conn.execute(
            f"""
            INSERT INTO {table} (id, shop_id, mem_key, value, source, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (mid, sid, key, value, source, now, now),
        )
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (mid,)).fetchone()
        return _row(row, layer, created=True)


def list_memories(*, shop_id: str | None = None, layer: Layer | None = None) -> list[dict[str, Any]]:
    sid = shop_id_or(shop_id)
    out: list[dict[str, Any]] = []
    layers: list[Layer] = [layer] if layer else ["personal", "business"]
    conn = get_connection()
    try:
        for ly in layers:
            rows = conn.execute(
                f"SELECT * FROM {_table(ly)} WHERE shop_id = ? AND status = 'active' ORDER BY updated_at DESC",
                (sid,),
            ).fetchall()
            out.extend(_row(r, ly) for r in rows)
    finally:
        conn.close()
    return out


def relevant(transcript: str, *, shop_id: str | None = None, limit: int = 12) -> dict[str, Any]:
    items = list_memories(shop_id=shop_id)
    n = normalize_text(transcript or "")
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        score = 1
        blob = normalize_text(f"{item['key']} {item['value']}")
        if item["key"] in {"preferred_language", "preferred_name", "explanation_style", "shop_name", "shop_type"}:
            score += 3
        if any(w in n for w in blob.split() if len(w) > 3):
            score += 2
        if "shop" in n and item["layer"] == "business":
            score += 2
        if any(w in n for w in ("me", "my", "i ", "नाम", "दुकान")) and item["layer"] == "personal":
            score += 1
        scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    picked = [s[1] for s in scored[:limit]]
    prefs = {p["key"]: p["value"] for p in picked}
    return {"items": picked, "prefs": prefs}


def get_preference(key: str, *, shop_id: str | None = None) -> str | None:
    sid = shop_id_or(shop_id)
    conn = get_connection()
    try:
        for table in ("personal_memories", "business_memories"):
            row = conn.execute(
                f"SELECT value FROM {table} WHERE shop_id = ? AND mem_key = ? AND status = 'active'",
                (sid, key),
            ).fetchone()
            if row:
                return row["value"]
    finally:
        conn.close()
    return None


def forget(memory_id: str, *, shop_id: str | None = None) -> dict[str, Any]:
    sid = shop_id_or(shop_id)
    now = _now()
    with atomic_connection() as conn:
        for layer in ("personal", "business"):
            table = _table(layer)  # type: ignore[arg-type]
            row = conn.execute(
                f"SELECT * FROM {table} WHERE id = ? AND shop_id = ?",
                (memory_id, sid),
            ).fetchone()
            if row is None:
                continue
            if row["status"] == "deleted":
                return {"ok": True, "deleted": True, "already": True, "id": memory_id}
            cur = conn.execute(
                f"UPDATE {table} SET status = 'deleted', updated_at = ? WHERE id = ? AND shop_id = ? AND status = 'active'",
                (now, memory_id, sid),
            )
            if cur.rowcount != 1:
                raise ApiError("Could not delete that memory.", 409, "conflict")
            return {"ok": True, "deleted": True, "already": False, "id": memory_id, "key": row["mem_key"]}
    raise ApiError("Memory not found.", 404, "not_found")


def forget_key(layer: Layer, key: str, *, shop_id: str | None = None) -> dict[str, Any]:
    sid = shop_id_or(shop_id)
    items = [m for m in list_memories(shop_id=sid, layer=layer) if m["key"] == key]
    if not items:
        raise ApiError("I do not have that memory stored.", 404, "not_found")
    return forget(items[0]["id"], shop_id=sid)


def forget_all(*, shop_id: str | None = None) -> int:
    sid = shop_id_or(shop_id)
    now = _now()
    n = 0
    with atomic_connection() as conn:
        for table in ("personal_memories", "business_memories"):
            cur = conn.execute(
                f"UPDATE {table} SET status = 'deleted', updated_at = ? WHERE shop_id = ? AND status = 'active'",
                (now, sid),
            )
            n += cur.rowcount
    return n


def _row(row, layer: Layer, **flags: bool) -> dict[str, Any]:
    data = {
        "id": row["id"],
        "shop_id": row["shop_id"],
        "layer": layer,
        "key": row["mem_key"],
        "value": row["value"],
        "source": row["source"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    data.update({k: v for k, v in flags.items() if v})
    return data
