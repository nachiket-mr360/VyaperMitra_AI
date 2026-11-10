from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from catalog import canonical_name, suggested_aliases
from config import Config
from db import atomic_connection
from errors import ApiError
from intents.confirm_speech import classify_confirm_speech
from intents.unclear import is_unclear_transcript, recovery_message
from intents.clarify import apply_fill, extract_fill, first_missing, question as clarify_question, wants_metric_choice
from intents.followup import parse_followup
from intents.language import (
    detect_input_language,
    low_confidence_prompt,
    normalize_mode,
    resolve_reply_language,
    stick_reply_language,
    tamil_limitation_message,
)
from intents.memory_parser import classify_candidate, extract_stable_facts, parse_memory_command
from intents.visualization import from_analytics_result
from intents.ops_parser import parse_shop_ops
from intents.parser import is_low_stock_list_query, parse_transcript
from intents.resolver import resolve_product
from intents.router import fallback_chat, is_greeting, llm_unavailable_reply, rule_route
from intents.schemas import ParseDraft
from intents import session_store
from speak import detect_language
from llm import gemini
from llm.validate import validate_llm_payload
from services import analytics as analytics_service
from services import memory as memory_service
from services import planner as planner_service
from services.products import create_product
from speak import (
    detect_language,
    new_product_sale_prompt,
    pending_wait_prompt,
    purchase_confirm_prompt,
    sale_confirm_prompt,
    sale_recorded_prompt,
    with_reply,
)
from services.sales import create_sale
from services.stock import record_purchase
from timeutil import now_business
from validate import ALLOWED_UNITS

logger = logging.getLogger("vyaparmitra.intents")

CHAT_INTENTS = frozenset(
    {
        "general_conversation",
        "general_question",
        "business_advice",
        "clarification",
    }
)


def _now() -> str:
    return now_business().isoformat()


def _cancel_open_actions(conn) -> None:
    conn.execute(
        "UPDATE pending_voice_actions SET status = 'superseded', updated_at = ? WHERE status = 'pending'",
        (_now(),),
    )


def _save_pending(payload: dict[str, Any], transcript: str) -> str:
    action_id = str(uuid.uuid4())
    now = _now()
    with atomic_connection() as conn:
        _cancel_open_actions(conn)
        conn.execute(
            """
            INSERT INTO pending_voice_actions
                (id, intent, status, payload_json, transcript, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?, ?, ?)
            """,
            (action_id, payload["intent"], json.dumps(payload), transcript, now, now),
        )
    return action_id


def _row_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "intent": row["intent"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"]),
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "transcript": row["transcript"],
        "created_at": row["created_at"],
    }


def _expired(created_at: str) -> bool:
    ttl = Config.INTENT_PENDING_TTL_SECONDS
    if ttl <= 0:
        return False
    created = datetime.fromisoformat(created_at)
    now = now_business()
    if created.tzinfo is None and now.tzinfo is not None:
        created = created.replace(tzinfo=now.tzinfo)
    elif created.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=created.tzinfo)
    return now - created > timedelta(seconds=ttl)


def _load(action_id: str) -> dict[str, Any]:
    with atomic_connection(immediate=False) as conn:
        row = conn.execute(
            "SELECT * FROM pending_voice_actions WHERE id = ?", (action_id,)
        ).fetchone()
    if row is None:
        raise ApiError("Pending action not found", 404, "not_found")
    return _row_dict(row)


def propose_sale_mutation(intent: str, payload: dict[str, Any], session_id: str | None, transcript: str = "") -> dict[str, Any]:
    sid = (session_id or "").strip()
    if not sid:
        raise ApiError("session_id is required", 400, "missing_field")
    body = dict(payload)
    body["intent"] = intent
    body["session_id"] = sid
    pid = _save_pending(body, transcript or intent)
    return {
        "ok": True,
        "needs_confirmation": True,
        "pending_id": pid,
        "executed": False,
        "intent": intent,
        "message": body.get("confirm_message") or "Confirm this change. Stock will update only after confirmation. This is not a cash refund.",
    }


def _reminder_confirm_line(lang: str, title: str, due_date: str, due_time: str | None) -> str:
    when = f"{due_date}" + (f" {due_time}" if due_time else "")
    lines = {
        "hi": f"'{title}' का रिमाइंडर {when} पर बनाने की पुष्टि करें?",
        "kn": f"'{title}' ಜ್ಞಾಪನೆ {when}ಕ್ಕೆ ಹಾಕೋಣವೇ?",
        "mr": f"'{title}' ची आठवण {when} ला सेट करायची पुष्टी कराल का?",
        "en": f"Create reminder '{title}' on {due_date}" + (f" at {due_time}" if due_time else "") + "?",
    }
    return lines.get(lang, lines["en"])


def _process_ops(ops: dict[str, Any], transcript: str, session_id: str | None = None) -> dict[str, Any]:
    intent = ops["intent"]
    base = {
        "ok": True,
        "transcript": transcript,
        "intent": intent,
        "product_query": None,
        "quantity": None,
        "unit": None,
        "sale_amount": None,
        "missing": ops.get("missing") or [],
        "candidates": [],
        "needs_confirmation": False,
        "pending_id": None,
        "create_product": False,
        "message": ops.get("message") or "",
        "error_code": None,
        "executed": False,
        "result": None,
        "parser": "rule_based",
        "language": ops.get("language"),
        "title": ops.get("title"),
        "due_date": ops.get("due_date"),
        "due_time": ops.get("due_time"),
        "pending_hour": ops.get("pending_hour"),
        "recurrence": ops.get("recurrence"),
        "analytics_topic": ops.get("analytics_topic"),
        "period": ops.get("period"),
    }
    if base["missing"]:
        return base
    if intent in {"show_sale", "correct_sale", "return_sale", "cancel_sale"}:
        from services.sale_lifecycle import (
            find_open_sales_with_product,
            last_open_sale_id,
            sale_detail,
        )

        pending_payload = None
        with atomic_connection(immediate=False) as conn:
            if intent == "show_sale":
                sid = last_open_sale_id(conn)
                if not sid:
                    base["ok"] = False
                    base["message"] = "No sale found."
                    return base
                base["executed"] = True
                base["result"] = sale_detail(conn, sid)
                base["message"] = f"Bill {sid}."
                return base
            if intent == "cancel_sale":
                sid = ops.get("sale_id")
                if not sid:
                    sid = last_open_sale_id(conn)
                if not sid:
                    base["ok"] = False
                    base["message"] = "No sale found to cancel."
                    return base
                pending_payload = {
                    "intent": "cancel_sale",
                    "sale_id": int(sid),
                    "session_id": session_id,
                    "confirm_message": f"Cancel bill {sid}? Stock will be restored. This is not a cash refund.",
                }
            elif intent == "return_sale":
                qname = ops.get("product_query") or ""
                resolved = resolve_product(qname)
                if not resolved.product:
                    base["ok"] = False
                    base["message"] = "Which product was returned?"
                    return base
                pid = int(resolved.product["id"])
                sids = find_open_sales_with_product(conn, pid)
                if not sids:
                    base["ok"] = False
                    base["message"] = "No open sale with that product."
                    return base
                if len(sids) > 1:
                    base["ok"] = False
                    base["message"] = "Which bill number was the return for?"
                    return base
                detail = sale_detail(conn, sids[0])
                line = next((ln for ln in detail["lines"] if ln["product_id"] == pid), None)
                if not line:
                    base["ok"] = False
                    base["message"] = "That product is not on the last matching bill."
                    return base
                pending_payload = {
                    "intent": "return_sale",
                    "sale_id": sids[0],
                    "line_key": line["line_key"],
                    "quantity": ops.get("quantity"),
                    "confirm_message": (
                        f"Record return of {ops.get('quantity')} {line.get('unit') or ''} "
                        f"{line.get('product_name')} on bill {sids[0]}? Stock will increase. Not a cash refund."
                    ),
                }
            elif intent == "correct_sale":
                sid = ops.get("sale_id") or last_open_sale_id(conn)
                if not sid:
                    base["ok"] = False
                    base["message"] = "No sale to correct."
                    return base
                detail = sale_detail(conn, int(sid))
                active = [
                    ln
                    for ln in detail.get("lines") or []
                    if not ln.get("removed") and float(ln.get("remaining_quantity") or ln.get("effective_quantity") or 0) > 0
                ]
                if len(active) != 1:
                    base["ok"] = False
                    base["message"] = "Which bill line should I correct? Say the product."
                    return base
                line = active[0]
                qty = ops.get("quantity")
                if qty is None:
                    qty = line.get("remaining_quantity") or line.get("effective_quantity")
                amount = ops.get("sale_amount")
                unit_price = line.get("unit_price")
                if amount is not None and qty:
                    unit_price = float(amount) / float(qty)
                if qty is None or unit_price is None:
                    base["missing"] = ["correction"]
                    base["message"] = f"Last bill is {sid}. Say the new quantity or price."
                    return base
                pending_payload = {
                    "intent": "correct_sale",
                    "sale_id": int(sid),
                    "line_key": line["line_key"],
                    "product_id": line.get("product_id"),
                    "quantity": qty,
                    "unit_price": unit_price,
                    "session_id": session_id,
                    "confirm_message": (
                        f"Correct bill {sid} {line.get('product_name') or ''} to "
                        f"{qty} {line.get('unit') or ''} at {unit_price} per unit? "
                        "Stock will update. This is not a cash refund."
                    ),
                }
        if pending_payload:
            if not (session_id or "").strip():
                base["ok"] = False
                base["message"] = "Session is required to change a bill."
                return base
            pending_payload["session_id"] = session_id
            pid = _save_pending(pending_payload, transcript)
            base["needs_confirmation"] = True
            base["pending_id"] = pid
            base["message"] = pending_payload["confirm_message"]
        return base
    if intent == "check_analytics":
        topic = ops.get("analytics_topic") or "sales"
        period = ops.get("period")
        base["executed"] = True
        base["result"] = analytics_service.voice_query(topic, period, ops.get("product"))
        viz = from_analytics_result(base["result"], force=bool(ops.get("force_chart")))
        base["visualization"] = viz
        base["message"] = "Shop figures from records."
        return base
    if intent == "daily_briefing":
        base["executed"] = True
        base["result"] = planner_service.briefing()
        base["message"] = "Today's briefing."
        return base
    if intent == "list_reminders":
        base["executed"] = True
        base["result"] = {"reminders": planner_service.list_reminders(status="open")}
        return base
    if intent == "list_notes":
        base["executed"] = True
        base["result"] = {"notes": planner_service.list_notes()}
        return base
    if intent == "complete_reminder":
        hits = planner_service.find_open_by_title(ops.get("title") or "")
        if len(hits) != 1:
            base["ok"] = False
            base["error_code"] = "ambiguous_reminder" if hits else "not_found"
            base["message"] = "Say the reminder title more clearly."
            return base
        payload = {
            "intent": intent,
            "reminder_id": hits[0]["id"],
            "confirm_message": f"Mark reminder '{hits[0]['title']}' complete?",
        }
        pid = _save_pending(payload, transcript)
        base["needs_confirmation"] = True
        base["pending_id"] = pid
        base["message"] = payload["confirm_message"]
        return base
    if intent == "create_reminder":
        if not ops.get("due_date"):
            base["missing"] = list(base["missing"] or []) + ["date"]
            base["message"] = "When should I remind you? Say a day or date."
            return base
        payload = {
            "intent": intent,
            "title": ops["title"],
            "due_date": ops["due_date"],
            "due_time": ops.get("due_time"),
            "recurrence": ops.get("recurrence") or "none",
            "weekday": ops.get("weekday"),
            "month_day": ops.get("month_day"),
            "language": ops.get("language") or "en",
            "confirm_message": _reminder_confirm_line(
                ops.get("language") or "en",
                ops["title"],
                ops["due_date"],
                ops.get("due_time"),
            ),
        }
        pid = _save_pending(payload, transcript)
        base["needs_confirmation"] = True
        base["pending_id"] = pid
        base["message"] = payload["confirm_message"]
        base["title"] = ops["title"]
        base["due_date"] = ops["due_date"]
        base["due_time"] = ops.get("due_time")
        base["recurrence"] = payload["recurrence"]
        return base
    if intent == "delete_reminder":
        hits = planner_service.find_open_by_title(ops.get("title") or "")
        if len(hits) != 1:
            base["ok"] = False
            base["error_code"] = "ambiguous_reminder" if hits else "not_found"
            base["message"] = "Which reminder should I delete?"
            return base
        payload = {
            "intent": intent,
            "reminder_id": hits[0]["id"],
            "confirm_message": f"Delete reminder '{hits[0]['title']}'?",
        }
        pid = _save_pending(payload, transcript)
        base["needs_confirmation"] = True
        base["pending_id"] = pid
        base["message"] = payload["confirm_message"]
        return base
    if intent == "create_note":
        payload = {
            "intent": intent,
            "body": ops["body"],
            "confirm_message": f"Save note: {ops['body']}?",
        }
        pid = _save_pending(payload, transcript)
        base["needs_confirmation"] = True
        base["pending_id"] = pid
        base["message"] = payload["confirm_message"]
        base["body"] = ops["body"]
        return base
    if intent == "delete_note":
        notes = planner_service.list_notes()
        q = (ops.get("title") or "").lower()
        hits = [n for n in notes if q and q in n["body"].lower()]
        if len(hits) != 1:
            base["ok"] = False
            base["error_code"] = "ambiguous_note" if hits else "not_found"
            base["message"] = "Which note should I delete?"
            return base
        payload = {
            "intent": intent,
            "note_id": hits[0]["id"],
            "confirm_message": f"Delete note: {hits[0]['body']}?",
        }
        pid = _save_pending(payload, transcript)
        base["needs_confirmation"] = True
        base["pending_id"] = pid
        base["message"] = payload["confirm_message"]
        return base
    base["ok"] = False
    base["error_code"] = "unsupported_intent"
    return base


def _envelope(
    transcript: str,
    *,
    intent: str,
    message: str,
    session_id: str | None,
    parser: str,
    result: Any = None,
    executed: bool = False,
    needs_confirmation: bool = False,
    pending_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "ok": True,
        "transcript": transcript,
        "intent": intent,
        "product_query": None,
        "quantity": None,
        "unit": None,
        "sale_amount": None,
        "missing": [],
        "candidates": [],
        "needs_confirmation": needs_confirmation,
        "pending_id": pending_id,
        "create_product": False,
        "message": message,
        "error_code": None,
        "executed": executed,
        "result": result,
        "parser": parser,
        "session_id": session_id,
    }
    if extra:
        payload.update(extra)
    out = with_reply(payload, transcript)
    _stamp_state(out)
    session_store.remember(session_id, transcript, out.get("reply_text") or message, out)
    return out


def _stamp_state(payload: dict[str, Any]) -> None:
    if payload.get("needs_confirmation"):
        payload["conversation_state"] = "awaiting_confirmation"
    elif payload.get("missing"):
        payload["conversation_state"] = "clarification"
        payload["needs_confirmation"] = False
        payload["executed"] = False
    elif payload.get("intent") in CHAT_INTENTS:
        payload["conversation_state"] = "general_conversation" if payload.get("intent") != "clarification" else "clarification"
    elif payload.get("intent") == "check_analytics" and payload.get("executed"):
        payload["conversation_state"] = "business_query"
    elif payload.get("executed") and payload.get("intent") not in CHAT_INTENTS:
        payload["conversation_state"] = "confirmed" if payload.get("intent") in {"confirmation"} else "business_query"
    else:
        payload["conversation_state"] = payload.get("conversation_state") or "business_query"


def _enter_clarification(payload: dict[str, Any], transcript: str, sid: str | None) -> dict[str, Any]:
    lang = payload.get("language") or detect_language(transcript)
    missing = list(payload.get("missing") or [])
    if payload.get("unclear_fill"):
        payload["message"] = recovery_message(lang)
    else:
        q = clarify_question(
            missing,
            lang=lang,
            product=payload.get("product_query") or payload.get("title"),
            intent=payload.get("intent") or "",
            pending_hour=payload.get("pending_hour"),
        )
        payload["message"] = q
    payload["needs_confirmation"] = False
    payload["executed"] = False
    payload["conversation_state"] = "clarification"
    if sid:
        row = session_store.ensure(sid)
        row["clarification_slot"] = {
            "intent": payload.get("intent"),
            "product_query": payload.get("product_query"),
            "quantity": payload.get("quantity"),
            "unit": payload.get("unit"),
            "sale_amount": payload.get("sale_amount"),
            "title": payload.get("title") or (payload.get("result") or {}).get("title") if isinstance(payload.get("result"), dict) else payload.get("title"),
            "due_date": payload.get("due_date"),
            "due_time": payload.get("due_time"),
            "pending_hour": payload.get("pending_hour"),
            "recurrence": payload.get("recurrence") or "none",
            "analytics_topic": payload.get("analytics_topic"),
            "period": payload.get("period"),
            "metric": payload.get("metric"),
            "missing": missing,
            "language": lang,
        }
    return payload


def _clear_slot(sid: str | None) -> None:
    if not sid:
        return
    session_store.ensure(sid)["clarification_slot"] = None


def _reply_out(payload: dict[str, Any], transcript: str, sid: str | None, t0: float, gemini_ms: float | None = None) -> dict[str, Any]:
    if payload.get("missing"):
        payload = _enter_clarification(payload, transcript, sid)
    else:
        _stamp_state(payload)
        if sid and payload.get("needs_confirmation"):
            _clear_slot(sid)
        elif sid and not payload.get("missing"):
            if payload.get("conversation_state") != "clarification":
                _clear_slot(sid)
    if sid:
        payload["language_mode"] = session_store.ensure(sid).get("language_mode") or "auto"
    out = with_reply(payload, transcript)
    if payload.get("visualization"):
        out["visualization"] = payload["visualization"]
    out["session_id"] = sid
    out["timings_ms"] = {
        "total": round((time.perf_counter() - t0) * 1000, 1),
        "gemini": gemini_ms,
        "intent": round((time.perf_counter() - t0) * 1000, 1),
    }
    logger.info(
        "intent_done intent=%s parser=%s gemini_ms=%s total_ms=%s",
        out.get("intent"),
        out.get("parser"),
        gemini_ms,
        out["timings_ms"]["total"],
    )
    session_store.remember(sid, transcript, out.get("reply_text") or out.get("message") or "", out)
    if out.get("needs_confirmation"):
        session_store.set_pending(sid, out.get("pending_id"))
    return out


def _maybe_extract_memories(transcript: str, intent: str, session_id: str | None = None) -> list[dict[str, Any]]:
    ctx = session_store.get(session_id) if session_id else None
    if ctx and ctx.get("skip_extract"):
        return []
    if intent in {"purchase_stock", "record_sale", "create_reminder", "confirmation", "cancellation"}:
        return []
    saved = []
    for fact in extract_stable_facts(transcript):
        kind = classify_candidate(transcript, fact)
        if kind in {"temporary", "transactional", "uncertain", "sensitive"}:
            continue
        if kind == "stable":
            try:
                row = memory_service.upsert(fact["layer"], fact["key"], fact["value"], source="user_stated")
                saved.append(row)
            except ApiError:
                continue
    return saved


def _handle_memory_command(transcript: str, session_id: str | None) -> dict[str, Any] | None:
    cmd = parse_memory_command(transcript)
    if not cmd:
        return None
    op = cmd.get("op")
    if op == "skip_extract":
        if session_id:
            session_store.ensure(session_id)["skip_extract"] = True
        return _envelope(
            transcript,
            intent="memory_skip",
            message="I will not store this conversation as long-term memory.",
            session_id=session_id,
            parser="memory",
        )
    if op == "list":
        layer = cmd.get("layer")
        items = memory_service.list_memories(layer=layer) if layer in {"personal", "business"} else memory_service.list_memories()
        if not items:
            msg = "I do not have stored personal memories yet." if layer == "personal" else "I do not have stored shop memories yet."
            if layer not in {"personal", "business"}:
                msg = "I do not have stored memories yet."
        else:
            lines = [f"{i['layer']}: {i['key']} = {i['value']}" for i in items]
            heading = "About you: " if layer == "personal" else "About your shop: " if layer == "business" else "Stored memories: "
            msg = heading + "; ".join(lines)
        return _envelope(transcript, intent="memory_list", message=msg, session_id=session_id, parser="memory", result={"memories": items})
    if op == "forget_key":
        try:
            memory_service.forget_key(cmd["layer"], cmd["key"])
            return _envelope(
                transcript,
                intent="memory_forget",
                message="I have removed that memory.",
                session_id=session_id,
                parser="memory",
                executed=True,
            )
        except ApiError as exc:
            return _envelope(
                transcript,
                intent="memory_forget",
                message=exc.message,
                session_id=session_id,
                parser="memory",
                extra={"ok": False, "error_code": exc.code},
            )
    if op == "forget_all":
        ctx = session_store.get(session_id) if session_id else None
        if ctx and ctx.get("forget_all_pending"):
            n = memory_service.forget_all()
            if session_id:
                session_store.ensure(session_id)["forget_all_pending"] = False
            return _envelope(
                transcript,
                intent="memory_forget",
                message=f"I have deleted {n} stored memories." if n else "There was nothing stored to delete.",
                session_id=session_id,
                parser="memory",
                executed=True,
            )
        if session_id:
            session_store.ensure(session_id)["forget_all_pending"] = True
        return _envelope(
            transcript,
            intent="memory_forget",
            message="Delete all stored personal and shop memories? Say yes to confirm.",
            session_id=session_id,
            parser="memory",
            needs_confirmation=True,
        )
    if op == "upsert":
        try:
            row = memory_service.upsert(cmd["layer"], cmd["key"], cmd["value"], source="user_stated")
            msg = "Updated." if row.get("updated") else "I will remember that." if not row.get("duplicate") else "I already had that saved."
            return _envelope(
                transcript,
                intent="memory_save",
                message=msg,
                session_id=session_id,
                parser="memory",
                executed=True,
                result=row,
            )
        except ApiError as exc:
            return _envelope(
                transcript,
                intent="memory_save",
                message=exc.message,
                session_id=session_id,
                parser="memory",
                extra={"ok": False, "error_code": exc.code},
            )
    return None


def _try_gemini(
    transcript: str, history: list[dict[str, str]] | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    if not gemini.configured():
        return None, None
    try:
        today = now_business().date().isoformat()
        try:
            raw = gemini.interpret(transcript, today=today, history=history)
        except TypeError:
            raw = gemini.interpret(transcript, today=today)
        return validate_llm_payload(raw), None
    except ApiError as exc:
        logger.warning("Gemini fallback error_code=%s", exc.code)
        return None, exc.code


def _advice_facts() -> dict[str, Any]:
    today = analytics_service.sales_today()
    yesterday = analytics_service.sales_yesterday()
    overview = analytics_service.voice_query("overview", "week")
    best = (overview.get("best_sellers") or [None])[0]
    return {
        "today_total_amount": today.get("total_amount"),
        "today_transactions": today.get("transactions"),
        "yesterday_total_amount": yesterday.get("total_amount"),
        "yesterday_transactions": yesterday.get("transactions"),
        "low_stock_count": len(overview.get("low_stock") or []),
        "top_product": (best or {}).get("name"),
        "profit_available": False,
        "cash_received_known": False,
        "note": "These are recorded shop figures only. Do not invent causes of change. Not profit or cash received.",
    }


def _chat_result(
    transcript: str,
    *,
    intent: str,
    session_id: str | None,
    llm_err: str | None,
    parser: str,
    language_mode: str = "auto",
    skip_llm: bool = False,
    t0: float | None = None,
) -> dict[str, Any]:
    t_chat = time.perf_counter()
    rel = memory_service.relevant(transcript)
    prefs = rel.get("prefs") or {}
    detected = detect_input_language(transcript)
    lang, detected, _conf = resolve_reply_language(transcript, mode=language_mode, detected=detected)
    hist = session_store.history(session_id)
    facts = _advice_facts() if intent == "business_advice" else None
    name = prefs.get("preferred_name")
    style = prefs.get("explanation_style")
    fb_route = intent if intent in {"business_advice", "general_question", "general_conversation"} else "unknown"
    text = fallback_chat(fb_route, transcript, lang)
    if llm_err:
        text = llm_unavailable_reply(lang, llm_err)
    if intent == "general_conversation" and name and len((transcript or "").split()) <= 8:
        if name.lower() not in text.lower():
            if lang == "en" and text:
                text = f"{name}, {text[0].lower() + text[1:]}"
            elif lang == "hi":
                text = f"{name} जी, {text}"
    gemini_ms = None
    if gemini.configured() and not skip_llm:
        g0 = time.perf_counter()
        try:
            try:
                text = gemini.chat_reply(
                    transcript,
                    language=lang,
                    history=hist,
                    facts=facts,
                    memories=rel.get("items") or [],
                    style=style,
                )
            except TypeError:
                try:
                    text = gemini.chat_reply(transcript, language=lang, history=hist, facts=facts)
                except TypeError:
                    text = gemini.chat_reply(transcript)
        except ApiError as exc:
            llm_err = exc.code
            logger.warning("gemini_chat_failed code=%s", exc.code)
            text = llm_unavailable_reply(lang, exc.code)
        except Exception:
            llm_err = "llm_unavailable"
            logger.warning("gemini_chat_failed code=llm_unavailable")
            text = llm_unavailable_reply(lang, "llm_unavailable")
        gemini_ms = round((time.perf_counter() - g0) * 1000, 1)
        logger.info("gemini_chat_ms=%s intent=%s", gemini_ms, intent)
    payload = {
        "ok": True,
        "transcript": transcript,
        "intent": intent,
        "product_query": None,
        "quantity": None,
        "unit": None,
        "sale_amount": None,
        "missing": [],
        "candidates": [],
        "needs_confirmation": False,
        "pending_id": None,
        "create_product": False,
        "message": text,
        "error_code": None,
        "executed": False,
        "result": facts,
        "parser": parser,
        "session_id": session_id,
        "visualization": None,
        "language_mode": language_mode,
        "language": lang,
    }
    if llm_err:
        payload["llm_fallback"] = llm_err
    saved = _maybe_extract_memories(transcript, intent, session_id)
    if saved:
        payload["memories_saved"] = [{"key": s["key"], "layer": s["layer"]} for s in saved]
    out = with_reply(payload, transcript)
    if lang in {"en", "hi", "kn", "mr"}:
        out["reply_language"] = lang
    out["detected_input_language"] = detected
    out["language_mode"] = language_mode
    started = t0 if t0 is not None else t_chat
    out["timings_ms"] = {
        "total": round((time.perf_counter() - started) * 1000, 1),
        "gemini": gemini_ms,
        "chat": round((time.perf_counter() - t_chat) * 1000, 1),
    }
    logger.info(
        "chat_done parser=%s skip_llm=%s gemini_ms=%s total_ms=%s lang=%s",
        parser,
        skip_llm,
        gemini_ms,
        out["timings_ms"]["total"],
        lang,
    )
    session_store.remember(session_id, transcript, out.get("reply_text") or text, out)
    return out


def _spoken_pending(transcript: str, session_id: str) -> dict[str, Any] | None:
    ctx = session_store.get(session_id)
    if not ctx or not ctx.get("pending_id"):
        return None
    decision = classify_confirm_speech(transcript)
    if decision not in {"yes", "no"}:
        return None
    if decision == "no":
        ops = parse_shop_ops(transcript)
        if ops and ops.get("intent") in {"cancel_sale", "correct_sale", "return_sale"}:
            return None
    intent = "confirmation" if decision == "yes" else "cancellation"
    try:
        raw = (
            confirm_action(ctx["pending_id"], session_id=session_id)
            if decision == "yes"
            else cancel_action(ctx["pending_id"])
        )
    except ApiError as exc:
        payload = {
            "ok": False,
            "transcript": transcript,
            "intent": intent,
            "product_query": None,
            "quantity": None,
            "unit": None,
            "sale_amount": None,
            "missing": [],
            "candidates": [],
            "needs_confirmation": False,
            "pending_id": ctx["pending_id"],
            "create_product": False,
            "message": exc.message,
            "error_code": exc.code,
            "executed": False,
            "result": None,
            "parser": "spoken_confirm",
            "session_id": session_id,
            "language_mode": ctx.get("language_mode") or "auto",
            "reply_language": ctx.get("last_reply_language") if ctx.get("last_reply_language") in {"en", "hi", "kn", "mr"} else None,
        }
        out = with_reply(payload, transcript)
        if exc.code in {"conflict", "not_found"}:
            session_store.set_pending(session_id, None)
        session_store.remember(session_id, transcript, out.get("reply_text") or exc.message, out)
        return out
    payload = {
        "ok": True,
        "transcript": transcript,
        "intent": intent,
        "product_query": None,
        "quantity": None,
        "unit": None,
        "sale_amount": None,
        "missing": [],
        "candidates": [],
        "needs_confirmation": False,
        "pending_id": ctx["pending_id"],
        "create_product": False,
        "message": raw.get("message") or "",
        "error_code": None,
        "executed": bool(raw.get("executed")),
        "cancelled": raw.get("cancelled"),
        "replayed": raw.get("replayed"),
        "result": raw.get("result"),
        "parser": "spoken_confirm",
        "session_id": session_id,
        "language_mode": session_store.ensure(session_id).get("language_mode") or "auto",
        "reply_language": ctx.get("last_reply_language") if ctx.get("last_reply_language") in {"en", "hi", "kn", "mr"} else None,
    }
    out = with_reply(payload, transcript)
    session_store.set_pending(session_id, None)
    session_store.remember(session_id, transcript, out.get("reply_text") or payload["message"], out)
    return out


def _pending_wait_reply(transcript: str, session_id: str, t0: float) -> dict[str, Any]:
    ctx = session_store.get(session_id) or {}
    lang, _, _ = stick_reply_language(
        transcript,
        mode=ctx.get("language_mode") or "auto",
        session_lang=ctx.get("last_reply_language"),
    )
    if lang not in {"en", "hi", "kn", "mr"}:
        lang = "en"
    msg = pending_wait_prompt(lang)
    payload = {
        "ok": True,
        "transcript": transcript,
        "intent": "clarification",
        "product_query": None,
        "quantity": None,
        "unit": None,
        "sale_amount": None,
        "missing": [],
        "candidates": [],
        "needs_confirmation": True,
        "pending_id": session_store.get(session_id).get("pending_id") if session_store.get(session_id) else None,
        "create_product": False,
        "message": msg,
        "error_code": None,
        "executed": False,
        "result": None,
        "parser": "spoken_confirm",
        "session_id": session_id,
        "language_mode": session_store.ensure(session_id).get("language_mode") or "auto",
    }
    return _reply_out(payload, transcript, session_id, t0)


def _apply_llm(v: dict[str, Any], transcript: str) -> dict[str, Any]:
    intent = v["intent"]
    if intent in {
        "create_reminder",
        "delete_reminder",
        "complete_reminder",
        "create_note",
        "delete_note",
        "check_analytics",
    }:
        ops = {
            "intent": intent,
            "title": v.get("title"),
            "body": v.get("body"),
            "due_date": v.get("due_date"),
            "due_time": v.get("due_time"),
            "recurrence": v.get("recurrence") or "none",
            "analytics_topic": v.get("analytics_topic"),
            "period": v.get("period"),
            "product": v.get("product"),
            "missing": v.get("missing") or [],
            "language": v.get("language") or "en",
            "message": "",
        }
        if intent == "check_analytics":
            rules = parse_shop_ops(transcript)
            if rules and rules.get("intent") == "check_analytics" and rules.get("analytics_topic"):
                ops["analytics_topic"] = rules["analytics_topic"]
                if rules.get("period") is not None:
                    ops["period"] = rules["period"]
                if rules.get("product"):
                    ops["product"] = rules["product"]
                if rules.get("language"):
                    ops["language"] = rules["language"]
        result = _process_ops(ops, transcript)
        result["parser"] = "gemini"
        result["llm_confidence"] = v["confidence"]
        return result
    draft = ParseDraft(
        intent=intent,
        product_query=v.get("product"),
        quantity=v.get("quantity"),
        unit=v.get("unit"),
        sale_amount=v.get("amount"),
        missing=[m for m in (v.get("missing") or []) if not (intent == "purchase_stock" and m in {"amount", "sale_amount"})],
        allow_create_product=True,
    )
    if (v.get("clarification_required") and draft.missing) or draft.missing:
        return {
            "ok": True,
            "transcript": transcript,
            "intent": intent,
            "product_query": draft.product_query,
            "quantity": draft.quantity,
            "unit": draft.unit,
            "sale_amount": draft.sale_amount,
            "missing": draft.missing,
            "candidates": [],
            "needs_confirmation": False,
            "pending_id": None,
            "create_product": False,
            "message": "Need more information." if draft.missing else "Please clarify.",
            "error_code": None,
            "executed": False,
            "result": None,
            "parser": "gemini",
            "llm_confidence": v["confidence"],
        }
    return _finish_inventory_draft(draft, transcript, parser="gemini", confidence=v["confidence"])


def _finish_inventory_draft(
    draft: ParseDraft,
    transcript: str,
    *,
    parser: str,
    confidence: float | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    base = {
        "ok": True,
        "transcript": transcript,
        "intent": draft.intent,
        "product_query": draft.product_query,
        "quantity": draft.quantity,
        "unit": draft.unit,
        "sale_amount": draft.sale_amount,
        "missing": draft.missing,
        "candidates": [],
        "needs_confirmation": False,
        "pending_id": None,
        "create_product": False,
        "message": draft.message,
        "error_code": draft.error_code,
        "executed": False,
        "result": None,
        "parser": parser,
        "llm_confidence": confidence,
    }
    if draft.error_code in {"empty_transcript", "unsupported_intent", "invalid_quantity", "invalid_unit"}:
        base["ok"] = False
        return base
    if draft.missing:
        return base

    resolved = resolve_product(draft.product_query)
    if resolved.ambiguous:
        base["ok"] = False
        base["error_code"] = "ambiguous_product"
        base["candidates"] = resolved.candidates
        base["message"] = "Several products match. Say the exact product name."
        return base

    if draft.intent == "check_stock":
        if is_low_stock_list_query(transcript):
            return _process_ops(
                {
                    "intent": "check_analytics",
                    "analytics_topic": "low_stock",
                    "period": None,
                    "missing": [],
                    "language": detect_language(transcript),
                },
                transcript,
            )
        if resolved.unknown or not resolved.product:
            base["ok"] = False
            base["error_code"] = "unknown_product"
            base["message"] = f"No product named “{draft.product_query}” was found."
            return base
        product = resolved.product
        base["product"] = product
        if not product.get("stock_known", True):
            base["result"] = {
                "name": product["name"],
                "quantity": None,
                "unit": product["unit"],
                "stock_known": False,
            }
            base["executed"] = True
            base["message"] = f"{product['name']}: stock has not been counted yet."
            return base
        base["result"] = {
            "name": product["name"],
            "quantity": product["current_stock"],
            "unit": product["unit"],
            "stock_known": True,
        }
        base["executed"] = True
        base["message"] = (
            f"{product['name']}: {product['current_stock']} {product['unit']} remaining."
        )
        return base

    ctx = session_store.get(session_id) if session_id else None
    lang, _, _ = stick_reply_language(
        transcript,
        mode=(ctx or {}).get("language_mode") or "auto",
        session_lang=(ctx or {}).get("last_reply_language"),
    )
    payload = _mutation_payload(draft, resolved, lang)
    base["language"] = lang
    base["reply_language"] = lang
    if payload.get("error_code"):
        base["ok"] = False
        base["error_code"] = payload["error_code"]
        base["message"] = payload["message"]
        base["create_product"] = payload.get("create_product", False)
        return base

    if session_id:
        payload["session_id"] = session_id
    if (
        draft.intent == "record_sale"
        and not payload.get("create_product")
        and payload.get("product_id")
        and draft.quantity is not None
        and draft.unit
        and draft.sale_amount is not None
        and not draft.missing
    ):
        try:
            committed = _commit_known_sale(payload, session_id)
        except ApiError as exc:
            base["ok"] = False
            base["error_code"] = exc.code
            base["message"] = exc.message
            base["executed"] = False
            return base
        base["needs_confirmation"] = False
        base["pending_id"] = None
        base["create_product"] = False
        base["product"] = payload.get("product")
        base["executed"] = True
        base["result"] = committed
        base["replayed"] = bool(committed.get("idempotent_replay"))
        sale = committed.get("sale") or {}
        amt = sale.get("total_amount", draft.sale_amount)
        name = (payload.get("product") or {}).get("name") or draft.product_query
        qty = draft.quantity
        unit = draft.unit or ""
        base["message"] = sale_recorded_prompt(lang, qty, unit, name, amt)
        return base
    pending_id = _save_pending(payload, transcript)
    base["needs_confirmation"] = True
    base["pending_id"] = pending_id
    base["create_product"] = payload.get("create_product", False)
    base["product"] = payload.get("product")
    base["suggested_aliases"] = payload.get("suggested_aliases") or []
    base["canonical_name"] = payload.get("canonical_name")
    base["message"] = payload["confirm_message"]
    return base


def _resume_clarification(transcript: str, sid: str | None, t0: float) -> dict[str, Any] | None:
    if not sid:
        return None
    ctx = session_store.get(sid) or {}
    slot = ctx.get("clarification_slot")
    if not slot:
        return None
    ops = parse_shop_ops(transcript)
    if (
        ops
        and ops.get("intent")
        and ops.get("intent") != slot.get("intent")
        and not ops.get("missing")
        and ops.get("intent") != "create_reminder"
    ):
        _clear_slot(sid)
        return None
    draft = parse_transcript(transcript)
    if is_low_stock_list_query(transcript):
        _clear_slot(sid)
        return None
    if (
        draft.intent in {"purchase_stock", "record_sale", "check_stock"}
        and draft.intent != slot.get("intent")
        and not draft.missing
        and draft.error_code not in {"unsupported_intent", "empty_transcript"}
        and not is_low_stock_list_query(transcript)
    ):
        _clear_slot(sid)
        return None
    fill = extract_fill(transcript)
    if ops and ops.get("intent") == slot.get("intent") == "create_reminder":
        if ops.get("due_time"):
            fill["time"] = ops["due_time"]
        if ops.get("pending_hour"):
            fill["hour"] = ops["pending_hour"]
        if ops.get("due_date") and not slot.get("due_date"):
            fill["due_date"] = ops["due_date"]
    if draft.intent == slot.get("intent") or draft.intent == "unknown":
        if draft.quantity is not None:
            fill["quantity"] = draft.quantity
        if draft.unit:
            fill["unit"] = draft.unit
        if draft.sale_amount is not None:
            fill["sale_amount"] = draft.sale_amount
        if draft.product_query:
            if "product" in (slot.get("missing") or []) or draft.error_code not in {
                "unsupported_intent",
                "empty_transcript",
            }:
                fill["product_query"] = draft.product_query
    merged = apply_fill(slot, fill)
    if not fill and draft.intent == "unknown" and not ops:
        payload = {
            "ok": True,
            "transcript": transcript,
            "intent": merged.get("intent") or "clarification",
            "product_query": merged.get("product_query"),
            "quantity": merged.get("quantity"),
            "unit": merged.get("unit"),
            "sale_amount": merged.get("sale_amount"),
            "missing": merged.get("missing") or ["quantity"],
            "candidates": [],
            "needs_confirmation": False,
            "pending_id": None,
            "create_product": False,
            "message": "",
            "error_code": None,
            "executed": False,
            "result": None,
            "parser": "clarification",
            "unclear_fill": True,
        }
        return _reply_out(payload, transcript, sid, t0)
    if merged.get("missing"):
        payload = {
            "ok": True,
            "transcript": transcript,
            "intent": merged.get("intent") or "clarification",
            "product_query": merged.get("product_query"),
            "quantity": merged.get("quantity"),
            "unit": merged.get("unit"),
            "sale_amount": merged.get("sale_amount"),
            "missing": merged["missing"],
            "candidates": [],
            "needs_confirmation": False,
            "pending_id": None,
            "create_product": False,
            "message": "",
            "error_code": None,
            "executed": False,
            "result": None,
            "parser": "clarification",
            "title": merged.get("title"),
            "due_date": merged.get("due_date"),
            "due_time": merged.get("due_time"),
            "pending_hour": merged.get("pending_hour"),
            "unclear_fill": not fill,
        }
        return _reply_out(payload, transcript, sid, t0)
    _clear_slot(sid)
    intent = merged.get("intent")
    if intent == "create_reminder":
        ops2 = {
            "intent": "create_reminder",
            "title": merged.get("title"),
            "due_date": merged.get("due_date"),
            "due_time": merged.get("due_time"),
            "recurrence": merged.get("recurrence") or "none",
            "missing": [],
            "language": merged.get("language") or "en",
        }
        return _reply_out(_process_ops(ops2, transcript), transcript, sid, t0)
    if intent == "check_analytics":
        ops2 = {
            "intent": "check_analytics",
            "analytics_topic": merged.get("analytics_topic") or "best_selling_product",
            "period": merged.get("period") or "today",
            "product": merged.get("product_query"),
            "missing": [],
            "language": merged.get("language") or "en",
        }
        return _reply_out(_process_ops(ops2, transcript), transcript, sid, t0)
    d = ParseDraft(
        intent=str(intent or "purchase_stock"),
        product_query=merged.get("product_query"),
        quantity=merged.get("quantity"),
        unit=merged.get("unit"),
        sale_amount=merged.get("sale_amount"),
        missing=[],
    )
    return _reply_out(_finish_inventory_draft(d, transcript, parser="clarification", session_id=sid), transcript, sid, t0)


def process_transcript(
    transcript: str,
    session_id: str | None = None,
    language_mode: str | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    sid = (session_id or "").strip() or None
    mode = normalize_mode(language_mode)
    if sid:
        session_store.ensure(sid)["language_mode"] = mode
    detected = detect_input_language(transcript or "")
    sess_lang = (session_store.get(sid) or {}).get("last_reply_language") if sid else None
    reply_lang, detected, conf = stick_reply_language(
        transcript or "", mode=mode, session_lang=sess_lang, detected=detected
    )
    if detected == "ta" and mode == "auto":
        return _envelope(
            transcript or "",
            intent="unsupported_language",
            message=tamil_limitation_message(reply_lang if reply_lang in {"en", "hi", "kn", "mr"} else "en"),
            session_id=sid,
            parser="language",
            extra={
                "reply_language": reply_lang if reply_lang in {"en", "hi", "kn", "mr"} else "en",
                "detected_input_language": "ta",
                "language_mode": mode,
            },
        )
    if mode == "auto" and conf < 0.4 and (transcript or "").strip() and detected != "en":
        return _envelope(
            transcript or "",
            intent="clarification",
            message=low_confidence_prompt(reply_lang),
            session_id=sid,
            parser="language",
            extra={
                "reply_language": reply_lang,
                "detected_input_language": detected,
                "language_mode": mode,
            },
        )
    if is_unclear_transcript(transcript):
        lang = detect_language(transcript or "") if (transcript or "").strip() else "en"
        if lang not in {"en", "hi", "kn", "mr"}:
            lang = "en"
        return _envelope(
            transcript or "",
            intent="unclear",
            message=recovery_message(lang, noisy=not (transcript or "").strip()),
            session_id=sid,
            parser="unclear",
            extra={"error_code": "unclear_speech", "reply_language": lang},
        )
    if sid:
        ctx = session_store.get(sid)
        if ctx and ctx.get("forget_all_pending"):
            decision = classify_confirm_speech(transcript)
            if decision == "yes":
                n = memory_service.forget_all()
                session_store.ensure(sid)["forget_all_pending"] = False
                return _envelope(
                    transcript,
                    intent="memory_forget",
                    message=f"I have deleted {n} stored memories." if n else "There was nothing stored to delete.",
                    session_id=sid,
                    parser="memory",
                    executed=True,
                )
            if decision == "no":
                session_store.ensure(sid)["forget_all_pending"] = False
                return _envelope(
                    transcript,
                    intent="memory_forget",
                    message="Kept your memories. Nothing was deleted.",
                    session_id=sid,
                    parser="memory",
                )
        spoken = _spoken_pending(transcript, sid)
        if spoken:
            return spoken
        ctx_pending = session_store.get(sid)
        if ctx_pending and ctx_pending.get("pending_id"):
            ops_hold = parse_shop_ops(transcript)
            if ops_hold and ops_hold.get("intent") in {
                "check_analytics",
                "cancel_sale",
                "correct_sale",
                "return_sale",
                "show_sale",
            }:
                if (
                    ctx_pending.get("last_sale_id")
                    and not ops_hold.get("sale_id")
                    and ops_hold.get("intent") in {"cancel_sale", "correct_sale", "return_sale", "show_sale"}
                ):
                    ops_hold["sale_id"] = ctx_pending["last_sale_id"]
                result = _process_ops(ops_hold, transcript, session_id=sid)
                return _reply_out(result, transcript, sid, t0)
            draft_hold = parse_transcript(transcript)
            if draft_hold.intent == "check_stock" and draft_hold.error_code != "unsupported_intent":
                result = _finish_inventory_draft(draft_hold, transcript, parser="rule_based", session_id=sid)
                return _reply_out(result, transcript, sid, t0)
            return _pending_wait_reply(transcript, sid, t0)
    mem = _handle_memory_command(transcript, sid)
    if mem:
        return mem
    resumed = _resume_clarification(transcript, sid, t0)
    if resumed:
        return resumed
    if wants_metric_choice(transcript):
        payload = {
            "ok": True,
            "transcript": transcript,
            "intent": "check_analytics",
            "product_query": None,
            "quantity": None,
            "unit": None,
            "sale_amount": None,
            "missing": ["metric"],
            "candidates": [],
            "needs_confirmation": False,
            "pending_id": None,
            "create_product": False,
            "message": "",
            "error_code": None,
            "executed": False,
            "result": None,
            "parser": "clarification",
            "analytics_topic": "best_selling_product",
            "period": "today",
        }
        return _reply_out(payload, transcript, sid, t0)
    fu = parse_followup(transcript, session_store.get(sid) if sid else None)
    if fu and fu.get("intent") == "product_follow" and fu.get("product"):
        follow = parse_transcript(f"how much {fu['product']} stock")
        follow.intent = "check_stock"
        follow.product_query = fu["product"]
        follow.error_code = None
        follow.message = ""
        follow.missing = []
        return _reply_out(_finish_inventory_draft(follow, transcript, parser="context", session_id=sid), transcript, sid, t0)
    if fu and fu.get("clarification"):
        return _envelope(
            transcript,
            intent="clarification",
            message=fu.get("message") or "Please say which sales, day, or product you mean.",
            session_id=sid,
            parser="followup",
        )
    if is_greeting(transcript):
        return _chat_result(
            transcript,
            intent="general_conversation",
            session_id=sid,
            llm_err=None,
            parser="rule_chat",
            language_mode=mode,
            skip_llm=True,
            t0=t0,
        )
    if fu and fu.get("followup"):
        ops = {
            "intent": "check_analytics",
            "analytics_topic": fu.get("analytics_topic") or "sales_summary",
            "period": fu.get("period"),
            "product": fu.get("product"),
            "force_chart": fu.get("force_chart"),
            "missing": [],
            "language": "en",
        }
        result = _process_ops(ops, transcript)
        return _reply_out(result, transcript, sid, t0)

    ops_early = parse_shop_ops(transcript)
    if ops_early:
        ctx_ops = session_store.get(sid) if sid else None
        if (
            ctx_ops
            and ctx_ops.get("last_sale_id")
            and not ops_early.get("sale_id")
            and ops_early.get("intent") in {"cancel_sale", "correct_sale", "return_sale", "show_sale"}
        ):
            ops_early["sale_id"] = ctx_ops["last_sale_id"]
        result = _process_ops(ops_early, transcript, session_id=sid)
        return _reply_out(result, transcript, sid, t0)

    draft_early = parse_transcript(transcript)
    if draft_early.intent in {"purchase_stock", "record_sale", "check_stock"} and draft_early.error_code != "unsupported_intent":
        result = _finish_inventory_draft(draft_early, transcript, parser="rule_based", session_id=sid)
        return _reply_out(result, transcript, sid, t0)

    ctx_guard = session_store.get(sid) if sid else None
    if ctx_guard and ctx_guard.get("last_sale_id") and len((transcript or "").split()) <= 6:
        draft_guard = parse_transcript(transcript)
        if draft_guard.intent in {"unknown", "check_stock"} and not parse_shop_ops(transcript):
            return _envelope(
                transcript,
                intent="clarification",
                message="Do you want to change the last bill, check stock, or record another sale?",
                session_id=sid,
                parser="context",
            )

    hist = session_store.history(sid)
    llm, llm_err, gemini_ms = None, None, None
    route = rule_route(transcript)
    if route in {"business_advice", "general_question"}:
        return _chat_result(
            transcript,
            intent=route,
            session_id=sid,
            llm_err=None,
            parser="gemini" if gemini.configured() else "rule_chat",
            language_mode=mode,
            skip_llm=not gemini.configured(),
            t0=t0,
        )

    shopish = bool(
        re.search(
            r"\b(sales?|stocks?|restock|remind(?:er|ers)?|purchas\w*|bought|sold|inventory|customers?|schedul\w*|meetings?|appointments?)\b|"
            r"बिक्री|स्टॉक|रिमाइंड|खरीद|खरीदा|लिया|ग्राहक|ಮಾರಾಟ|ಸ್ಟಾಕ್|विक्री|खरेदी|ಖರೀದಿ",
            transcript or "",
            re.I,
        )
    )
    if shopish and gemini.configured():
        g0 = time.perf_counter()
        llm, llm_err = _try_gemini(transcript, history=hist)
        gemini_ms = round((time.perf_counter() - g0) * 1000, 1)
        if llm and llm["intent"] in CHAT_INTENTS:
            return _chat_result(
                transcript,
                intent=llm["intent"],
                session_id=sid,
                llm_err=None,
                parser="gemini",
                language_mode=mode,
                skip_llm=False,
                t0=t0,
            )
        if llm and llm["intent"] not in {"unknown", "confirmation", "cancellation"}:
            applied = _apply_llm(llm, transcript)
            return _reply_out(applied, transcript, sid, t0, gemini_ms)
        if llm_err or llm is not None:
            return _chat_result(
                transcript,
                intent="clarification",
                session_id=sid,
                llm_err=llm_err,
                parser="rule_chat",
                language_mode=mode,
                skip_llm=True,
                t0=t0,
            )

    ctx = session_store.get(sid)
    if ctx and ctx.get("last_product") and ctx.get("last_intent") == "check_stock":
        follow = parse_transcript(transcript)
        if follow.intent == "unknown" and follow.product_query:
            follow.intent = "check_stock"
            follow.error_code = None
            follow.message = ""
            follow.missing = []
            result = _finish_inventory_draft(follow, transcript, parser="context", session_id=sid)
            return _reply_out(result, transcript, sid, t0)
        about = re.search(r"(?:what about|and)\s+([a-zA-Z\u0900-\u097F]{2,40})\??", transcript or "", re.I)
        if about and about.group(1).lower() not in {"yesterday", "today", "it", "that"}:
            follow.intent = "check_stock"
            follow.product_query = about.group(1)
            follow.error_code = None
            follow.message = ""
            follow.missing = []
            result = _finish_inventory_draft(follow, transcript, parser="context", session_id=sid)
            return _reply_out(result, transcript, sid, t0)

    if gemini.configured():
        return _chat_result(
            transcript,
            intent="general_question",
            session_id=sid,
            llm_err=llm_err,
            parser="gemini",
            language_mode=mode,
            skip_llm=False,
            t0=t0,
        )
    return _chat_result(
        transcript,
        intent="clarification",
        session_id=sid,
        llm_err=llm_err,
        parser="rule_chat",
        language_mode=mode,
        skip_llm=True,
        t0=t0,
    )


def _mutation_payload(draft: ParseDraft, resolved, lang: str = "en") -> dict[str, Any]:
    if draft.unit not in ALLOWED_UNITS:
        return {"error_code": "invalid_unit", "message": "That unit is not supported."}

    if resolved.unknown:
        if not draft.allow_create_product:
            return {
                "error_code": "unknown_product",
                "message": f"No product named “{draft.product_query}” was found.",
            }
        aliases = suggested_aliases(draft.product_query or "")
        canon = canonical_name(draft.product_query or "")
        alias_txt = ", ".join(a["alias"] for a in aliases[:8])
        if draft.intent == "purchase_stock":
            return {
                "intent": "purchase_stock",
                "product_id": None,
                "product_query": draft.product_query,
                "canonical_name": canon,
                "suggested_aliases": aliases,
                "quantity": draft.quantity,
                "unit": draft.unit,
                "unit_cost": None,
                "create_product": True,
                "confirm_message": (
                    f"New product “{canon}” ({alias_txt}). Confirm to create it and add "
                    f"{draft.quantity} {draft.unit} as first counted stock."
                ),
            }
        if draft.intent == "record_sale":
            return {
                "intent": "record_sale",
                "product_id": None,
                "product_query": draft.product_query,
                "canonical_name": canon,
                "suggested_aliases": aliases,
                "quantity": draft.quantity,
                "unit": draft.unit,
                "sale_amount": draft.sale_amount,
                "create_product": True,
                "skip_stock_decrement": True,
                "payment_status": "unknown",
                "confirm_message": new_product_sale_prompt(
                    lang, canon, draft.quantity, draft.unit or "", draft.sale_amount
                ),
            }
        return {
            "error_code": "unknown_product",
            "message": f"No product named “{draft.product_query}” was found.",
        }

    product = resolved.product
    assert product is not None
    if draft.unit != product["unit"]:
        return {
            "error_code": "incompatible_unit",
            "message": f"Product uses {product['unit']}, not {draft.unit}. Units were not converted.",
        }

    if draft.intent == "purchase_stock":
        return {
            "intent": "purchase_stock",
            "product_id": product["id"],
            "product": product,
            "product_query": draft.product_query,
            "quantity": draft.quantity,
            "unit": draft.unit,
            "unit_cost": None,
            "create_product": False,
            "confirm_message": purchase_confirm_prompt(
                lang, draft.quantity, draft.unit or "", product["name"]
            ),
        }

    unknown_stock = not product.get("stock_known", True)
    extra = {
        "hi": " स्टॉक गिना नहीं है, मात्रा नहीं बदलेगी।" if unknown_stock else " भुगतान प्राप्त नहीं माना गया।",
        "kn": " ಸ್ಟಾಕ್ ಎಣಿಸಿಲ್ಲ, ಪ್ರಮಾಣ ಬದಲಾಗುವುದಿಲ್ಲ." if unknown_stock else " ಪಾವತಿ ಸ್ವೀಕೃತವೆಂದು ಗುರುತಿಸಿಲ್ಲ.",
        "mr": " स्टॉक मोजलेला नाही, प्रमाण बदलणार नाही." if unknown_stock else " पेमेंट मिळाले असे मानले नाही.",
        "en": (
            " Stock is not counted, so quantity on hand will not change."
            if unknown_stock
            else " Payment is not marked as received."
        ),
    }.get(lang, "")
    return {
        "intent": "record_sale",
        "product_id": product["id"],
        "product": product,
        "product_query": draft.product_query,
        "quantity": draft.quantity,
        "unit": draft.unit,
        "sale_amount": draft.sale_amount,
        "create_product": False,
        "skip_stock_decrement": unknown_stock,
        "payment_status": "unknown",
        "confirm_message": sale_confirm_prompt(
            lang, draft.quantity, draft.unit or "", product["name"], draft.sale_amount, extra
        ),
    }


def confirm_action(pending_id: str, session_id: str | None = None) -> dict[str, Any]:
    if not pending_id:
        raise ApiError("Missing pending_id", 400, "missing_field")

    with atomic_connection() as conn:
        row = conn.execute(
            "SELECT * FROM pending_voice_actions WHERE id = ?", (pending_id,)
        ).fetchone()
        if row is None:
            raise ApiError("Pending action not found", 404, "not_found")
        data = _row_dict(row)

        if data["status"] == "confirmed" and data["result"] is not None:
            return {
                "ok": True,
                "executed": True,
                "replayed": True,
                "pending_id": pending_id,
                "intent": data["intent"],
                "result": data["result"],
                "message": "This action was already confirmed.",
            }

        if data["status"] == "pending" and _expired(data["created_at"]):
            conn.execute(
                "UPDATE pending_voice_actions SET status = 'expired', updated_at = ? WHERE id = ? AND status = 'pending'",
                (_now(), pending_id),
            )
            conn.execute("COMMIT")
            raise ApiError("This action has expired.", 409, "conflict")

        if data["status"] != "pending":
            raise ApiError("This action is no longer pending.", 409, "conflict")

        owned = (data["payload"] or {}).get("session_id")
        g1 = data["intent"] in {"cancel_sale", "return_sale", "correct_sale"}
        if g1:
            if not owned or not session_id or str(session_id) != str(owned):
                raise ApiError("This confirmation does not belong to this session.", 403, "forbidden")
        elif owned:
            if not session_id or str(session_id) != str(owned):
                raise ApiError("This confirmation does not belong to this session.", 403, "forbidden")

        claim = conn.execute(
            """
            UPDATE pending_voice_actions
            SET status = 'confirming', updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (_now(), pending_id),
        )
        if claim.rowcount != 1:
            raise ApiError("This action is no longer pending.", 409, "conflict")

        intent = data["intent"]
        payload = data["payload"]
        if intent == "purchase_stock":
            result = _exec_purchase(payload, conn)
        elif intent == "record_sale":
            result = _exec_sale(payload, pending_id, conn)
        elif intent == "create_reminder":
            result = {"reminder": planner_service.create_reminder(
                payload["title"],
                payload["due_date"],
                payload.get("due_time"),
                payload.get("recurrence") or "none",
                payload.get("weekday"),
                payload.get("month_day"),
                payload.get("language") or "en",
                conn=conn,
            )}
        elif intent == "delete_reminder":
            result = {"reminder": planner_service.delete_reminder(int(payload["reminder_id"]), conn=conn)}
        elif intent == "complete_reminder":
            result = {"reminder": planner_service.complete_reminder(int(payload["reminder_id"]), conn=conn)}
        elif intent == "create_note":
            result = {"note": planner_service.create_note(payload["body"], conn=conn)}
        elif intent == "delete_note":
            result = {"note": planner_service.delete_note(int(payload["note_id"]), conn=conn)}
        elif intent == "cancel_sale":
            from services.sale_lifecycle import cancel_sale as lc_cancel

            sale, replayed = lc_cancel(
                int(payload["sale_id"]),
                idempotency_key=f"voice:{pending_id}:cancel",
                conn=conn,
            )
            result = {"sale": sale, "idempotent_replay": replayed}
        elif intent == "return_sale":
            from services.sale_lifecycle import return_qty as lc_return

            sale, replayed = lc_return(
                int(payload["sale_id"]),
                line_key=payload["line_key"],
                quantity=payload["quantity"],
                idempotency_key=f"voice:{pending_id}:return",
                conn=conn,
            )
            result = {"sale": sale, "idempotent_replay": replayed}
        elif intent == "correct_sale":
            from services.sale_lifecycle import correct_line as lc_correct

            sale, replayed = lc_correct(
                int(payload["sale_id"]),
                line_key=payload.get("line_key"),
                product_id=payload.get("product_id"),
                quantity=payload.get("quantity"),
                unit_price=payload.get("unit_price"),
                add_line=bool(payload.get("add_line")),
                remove_line=bool(payload.get("remove_line")),
                idempotency_key=f"voice:{pending_id}:correct",
                conn=conn,
            )
            result = {"sale": sale, "idempotent_replay": replayed}
        else:
            raise ApiError("This action cannot be confirmed.", 400, "invalid_value")

        conn.execute(
            """
            UPDATE pending_voice_actions
            SET status = 'confirmed', result_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(result), _now(), pending_id),
        )

        lang = (payload.get("language") if isinstance(payload, dict) else None) or "en"
        done = "Done."
        if intent == "create_reminder":
            done = {
                "hi": "आपका रिमाइंडर सेट हो गया।",
                "kn": "ನಿಮ್ಮ ಜ್ಞಾಪನೆ ಹಾಕಲಾಗಿದೆ.",
                "mr": "तुमची आठवण सेट झाली.",
                "en": "Your reminder is set.",
            }.get(lang, "Your reminder is set.")
        if session_id:
            session_store.set_pending(session_id, None)
            if isinstance(result, dict) and isinstance(result.get("sale"), dict):
                row_s = session_store.ensure(session_id)
                row_s["last_sale_id"] = result["sale"].get("id")
                row_s["last_sale_result"] = result["sale"]
        return {
            "ok": True,
            "executed": True,
            "replayed": False,
            "pending_id": pending_id,
            "intent": intent,
            "result": result,
            "message": done,
        }


def cancel_action(pending_id: str) -> dict[str, Any]:
    if not pending_id:
        raise ApiError("Missing pending_id", 400, "missing_field")
    row = _load(pending_id)
    if row["status"] == "cancelled":
        return {"ok": True, "cancelled": True, "pending_id": pending_id, "message": "Already cancelled."}
    if row["status"] != "pending":
        raise ApiError("This action is no longer pending.", 409, "conflict")
    now = _now()
    with atomic_connection() as conn:
        conn.execute(
            "UPDATE pending_voice_actions SET status = 'cancelled', updated_at = ? WHERE id = ? AND status = 'pending'",
            (now, pending_id),
        )
    return {"ok": True, "cancelled": True, "pending_id": pending_id, "message": "Cancelled. Nothing was changed."}


def _commit_known_sale(payload: dict[str, Any], session_id: str | None) -> dict[str, Any]:
    fp = f"{payload.get('product_id')}|{payload.get('quantity')}|{payload.get('sale_amount')}|{payload.get('unit')}"
    if session_id:
        row = session_store.ensure(session_id)
        last_fp = row.get("last_sale_fp")
        last_ts = float(row.get("last_sale_ts") or 0)
        if last_fp == fp and (time.time() - last_ts) < 12 and row.get("last_sale_result"):
            return {"sale": row["last_sale_result"], "idempotent_replay": True}
    key = str(uuid.uuid4())
    with atomic_connection() as conn:
        result = _exec_sale(payload, key, conn)
    if session_id:
        row = session_store.ensure(session_id)
        row["last_sale_fp"] = fp
        row["last_sale_ts"] = time.time()
        if isinstance(result.get("sale"), dict):
            row["last_sale_id"] = result["sale"].get("id")
            row["last_sale_result"] = result["sale"]
    return result


def _exec_purchase(payload: dict[str, Any], conn) -> dict[str, Any]:
    product_id = payload.get("product_id")
    if payload.get("create_product") and not product_id:
        created = create_product(payload["product_query"], payload["unit"], conn=conn)
        product_id = created["id"]
    movement = record_purchase(
        int(product_id),
        payload["quantity"],
        payload.get("unit_cost"),
        notes="voice purchase",
        conn=conn,
    )
    return {"purchase": movement, "product_id": product_id}


def _exec_sale(payload: dict[str, Any], pending_id: str, conn) -> dict[str, Any]:
    product_id = payload.get("product_id")
    if payload.get("create_product") and not product_id:
        created = create_product(payload["product_query"], payload["unit"], conn=conn)
        product_id = created["id"]
    sale, replayed = create_sale(
        [
            {
                "product_id": int(product_id),
                "quantity": payload["quantity"],
                "line_total": payload["sale_amount"],
            }
        ],
        idempotency_key=f"voice:{pending_id}",
        notes="voice sale",
        payment_status="unknown",
        conn=conn,
    )
    return {"sale": sale, "idempotent_replay": replayed}
