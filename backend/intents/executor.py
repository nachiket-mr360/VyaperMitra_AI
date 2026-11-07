from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from config import Config
from db import atomic_connection
from errors import ApiError
from intents.parser import parse_transcript
from intents.resolver import resolve_product
from intents.schemas import ParseDraft
from services.products import create_product
from services.sales import create_sale
from services.stock import record_purchase
from timeutil import now_business
from validate import ALLOWED_UNITS


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


def process_transcript(transcript: str) -> dict[str, Any]:
    draft = parse_transcript(transcript)
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
        "parser": "rule_based",
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
        if resolved.unknown or not resolved.product:
            base["ok"] = False
            base["error_code"] = "unknown_product"
            base["message"] = f"No product named “{draft.product_query}” was found."
            return base
        product = resolved.product
        base["product"] = product
        base["result"] = {
            "name": product["name"],
            "quantity": product["current_stock"],
            "unit": product["unit"],
        }
        base["executed"] = True
        base["message"] = (
            f"{product['name']}: {product['current_stock']} {product['unit']} remaining."
        )
        return base

    payload = _mutation_payload(draft, resolved)
    if payload.get("error_code"):
        base["ok"] = False
        base["error_code"] = payload["error_code"]
        base["message"] = payload["message"]
        base["create_product"] = payload.get("create_product", False)
        return base

    pending_id = _save_pending(payload, transcript)
    base["needs_confirmation"] = True
    base["pending_id"] = pending_id
    base["create_product"] = payload.get("create_product", False)
    base["product"] = payload.get("product")
    base["message"] = payload["confirm_message"]
    return base


def _mutation_payload(draft: ParseDraft, resolved) -> dict[str, Any]:
    if draft.unit not in ALLOWED_UNITS:
        return {"error_code": "invalid_unit", "message": "That unit is not supported."}

    if resolved.unknown:
        if draft.intent == "purchase_stock":
            return {
                "intent": "purchase_stock",
                "product_id": None,
                "product_query": draft.product_query,
                "quantity": draft.quantity,
                "unit": draft.unit,
                "unit_cost": None,
                "create_product": True,
                "confirm_message": (
                    f"No product named “{draft.product_query}”. Confirm to create it and add "
                    f"{draft.quantity} {draft.unit}."
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
            "confirm_message": (
                f"Add {draft.quantity} {draft.unit} of {product['name']} to stock? "
                "Purchase cost was not given and will not be invented."
            ),
        }

    return {
        "intent": "record_sale",
        "product_id": product["id"],
        "product": product,
        "product_query": draft.product_query,
        "quantity": draft.quantity,
        "unit": draft.unit,
        "sale_amount": draft.sale_amount,
        "create_product": False,
        "payment_status": "unknown",
        "confirm_message": (
            f"Record sale of {draft.quantity} {draft.unit} of {product['name']} "
            f"for {draft.sale_amount} INR? Payment is not marked as received."
        ),
    }


def confirm_action(pending_id: str) -> dict[str, Any]:
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

        return {
            "ok": True,
            "executed": True,
            "replayed": False,
            "pending_id": pending_id,
            "intent": intent,
            "result": result,
            "message": "Done.",
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
    sale, replayed = create_sale(
        [
            {
                "product_id": payload["product_id"],
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
