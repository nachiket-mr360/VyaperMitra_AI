from __future__ import annotations

from flask import Blueprint, jsonify, request

from errors import ApiError
from services import sales as sales_service
from timeutil import parse_business_date
from validate import optional_str, require_int_id, require_json_object, require_positive

bp = Blueprint("sales", __name__)


@bp.post("/api/sales")
def create_sale():
    body = require_json_object(request.get_json(silent=True))
    raw_items = body.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ApiError("items must be a non-empty array", 400, "invalid_type")
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ApiError("Each item must be an object", 400, "invalid_type")
        product_id = require_int_id(raw.get("product_id"), "product_id")
        quantity = require_positive(raw, "quantity")
        item: dict = {"product_id": product_id, "quantity": quantity}
        if "line_total" in raw and raw["line_total"] is not None:
            if isinstance(raw["line_total"], bool) or not isinstance(raw["line_total"], (int, float)):
                raise ApiError("line_total must be a number", 400, "invalid_type")
            if raw["line_total"] < 0:
                raise ApiError("line_total cannot be negative", 400, "invalid_value")
            item["line_total"] = float(raw["line_total"])
        elif "unit_price" in raw:
            if isinstance(raw["unit_price"], bool) or not isinstance(raw["unit_price"], (int, float)):
                raise ApiError("unit_price must be a number", 400, "invalid_type")
            if raw["unit_price"] < 0:
                raise ApiError("unit_price cannot be negative", 400, "invalid_value")
            item["unit_price"] = float(raw["unit_price"])
        else:
            raise ApiError("Each item needs unit_price or line_total", 400, "missing_field")
        items.append(item)

    idem = optional_str(body, "idempotency_key", max_len=80)
    notes = optional_str(body, "notes")
    payment = optional_str(body, "payment_status", max_len=16) or "unknown"
    day = optional_str(body, "transaction_date", max_len=10)
    if day:
        try:
            day = parse_business_date(day)
        except ValueError:
            raise ApiError("transaction_date must be YYYY-MM-DD", 400, "invalid_value") from None

    sale, replayed = sales_service.create_sale(
        items,
        idempotency_key=idem,
        notes=notes,
        payment_status=payment,
        transaction_date=day,
    )
    status = 200 if replayed else 201
    return jsonify({"ok": True, "sale": sale, "replayed": replayed}), status


@bp.get("/api/sales")
def list_sales():
    day = request.args.get("date")
    if day:
        try:
            day = parse_business_date(day)
        except ValueError:
            raise ApiError("date must be YYYY-MM-DD", 400, "invalid_value") from None
    return jsonify({"ok": True, "sales": sales_service.list_sales(on_date=day)})


@bp.get("/api/sales/<int:sale_id>")
def get_sale(sale_id: int):
    return jsonify({"ok": True, "sale": sales_service.get_sale(sale_id)})
