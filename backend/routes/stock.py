from __future__ import annotations

from flask import Blueprint, jsonify, request

from errors import ApiError
from services import stock as stock_service
from services.stock import ALLOWED_MOVEMENTS
from validate import optional_number, optional_str, require_int_id, require_json_object, require_number, require_positive

bp = Blueprint("stock", __name__)


def _product_id(body: dict) -> int:
    return require_int_id(body.get("product_id"), "product_id")


def _reject_spoofed_type(body: dict, expected: str) -> None:
    if "movement_type" in body and body["movement_type"] != expected:
        raise ApiError("Invalid movement type for this endpoint", 400, "invalid_value")
    if expected not in ALLOWED_MOVEMENTS:
        raise ApiError("Invalid movement type", 400, "invalid_value")


@bp.post("/api/stock/opening")
def opening():
    body = require_json_object(request.get_json(silent=True))
    _reject_spoofed_type(body, "opening")
    cost = optional_number(body, "unit_cost")
    if cost is not None and cost < 0:
        raise ApiError("unit_cost cannot be negative", 400, "invalid_value")
    data = stock_service.record_opening(
        _product_id(body),
        require_positive(body, "quantity"),
        cost,
        optional_str(body, "notes"),
    )
    return jsonify({"ok": True, "movement": data}), 201


@bp.post("/api/stock/purchase")
def purchase():
    body = require_json_object(request.get_json(silent=True))
    _reject_spoofed_type(body, "purchase")
    cost = optional_number(body, "unit_cost")
    if cost is not None and cost < 0:
        raise ApiError("unit_cost cannot be negative", 400, "invalid_value")
    data = stock_service.record_purchase(
        _product_id(body),
        require_positive(body, "quantity"),
        cost,
        optional_str(body, "notes"),
    )
    return jsonify({"ok": True, "movement": data}), 201


@bp.post("/api/stock/adjustment")
def adjustment():
    body = require_json_object(request.get_json(silent=True))
    _reject_spoofed_type(body, "adjustment")
    quantity = require_number(body, "quantity")
    if quantity == 0:
        raise ApiError("quantity cannot be zero", 400, "invalid_value")
    data = stock_service.record_adjustment(
        _product_id(body),
        quantity,
        optional_str(body, "notes"),
    )
    return jsonify({"ok": True, "movement": data}), 201


@bp.get("/api/stock")
def current_stock():
    return jsonify({"ok": True, "stock": stock_service.list_stock()})


@bp.get("/api/stock/low")
def low_stock():
    return jsonify({"ok": True, "stock": stock_service.list_stock(low_only=True)})


@bp.get("/api/stock/movements")
def movements():
    raw = request.args.get("product_id")
    product_id = require_int_id(raw, "product_id") if raw else None
    return jsonify({"ok": True, "movements": stock_service.list_movements(product_id)})
