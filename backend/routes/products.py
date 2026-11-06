from __future__ import annotations

from flask import Blueprint, jsonify, request

from services import products as product_service
from validate import (
    optional_number,
    optional_str,
    reject_protected_product_fields,
    require_json_object,
    require_non_negative,
    require_str,
    require_unit,
)

bp = Blueprint("products", __name__)


@bp.post("/api/products")
def create_product():
    body = require_json_object(request.get_json(silent=True))
    reject_protected_product_fields(body)
    name = require_str(body, "name")
    unit = require_unit(require_str(body, "unit", max_len=32))
    threshold = optional_number(body, "low_stock_threshold")
    if threshold is None:
        threshold = 0
    if threshold < 0:
        from errors import ApiError

        raise ApiError("low_stock_threshold cannot be negative", 400, "invalid_value")
    opening = optional_number(body, "opening_stock")
    if opening is not None and opening <= 0:
        from errors import ApiError

        raise ApiError("opening_stock must be greater than 0", 400, "invalid_value")
    cost = optional_number(body, "opening_unit_cost")
    if cost is not None and cost < 0:
        from errors import ApiError

        raise ApiError("opening_unit_cost cannot be negative", 400, "invalid_value")
    data = product_service.create_product(
        name,
        unit,
        low_stock_threshold=threshold,
        opening_stock=opening,
        opening_unit_cost=cost,
    )
    return jsonify({"ok": True, "product": data}), 201


@bp.get("/api/products")
def list_products():
    include = request.args.get("include_inactive", "").lower() in {"1", "true", "yes"}
    return jsonify({"ok": True, "products": product_service.list_products(include_inactive=include)})


@bp.get("/api/products/<int:product_id>")
def get_product(product_id: int):
    return jsonify({"ok": True, "product": product_service.get_product_detail(product_id)})


@bp.patch("/api/products/<int:product_id>")
def update_product(product_id: int):
    body = require_json_object(request.get_json(silent=True))
    reject_protected_product_fields(body)
    fields = {}
    if "name" in body:
        fields["name"] = require_str(body, "name")
    if "unit" in body:
        fields["unit"] = require_unit(require_str(body, "unit", max_len=32))
    if "low_stock_threshold" in body:
        fields["low_stock_threshold"] = require_non_negative(body, "low_stock_threshold")
    if "active" in body:
        if not isinstance(body["active"], bool):
            from errors import ApiError

            raise ApiError("active must be a boolean", 400, "invalid_type")
        fields["active"] = body["active"]
    return jsonify({"ok": True, "product": product_service.update_product(product_id, fields)})


@bp.post("/api/products/<int:product_id>/deactivate")
def deactivate(product_id: int):
    return jsonify({"ok": True, "product": product_service.deactivate_product(product_id)})


@bp.post("/api/products/<int:product_id>/aliases")
def add_alias(product_id: int):
    body = require_json_object(request.get_json(silent=True))
    alias = require_str(body, "alias")
    language = optional_str(body, "language", max_len=16) or "und"
    data = product_service.add_alias(product_id, alias, language)
    return jsonify({"ok": True, "alias": data}), 201


@bp.put("/api/products/<int:product_id>/low-stock-threshold")
def set_threshold(product_id: int):
    body = require_json_object(request.get_json(silent=True))
    value = require_non_negative(body, "low_stock_threshold")
    product = product_service.update_product(product_id, {"low_stock_threshold": value})
    return jsonify({"ok": True, "product": product})
