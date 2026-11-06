from __future__ import annotations

from flask import Blueprint, jsonify, request

from errors import ApiError
from services import analytics as analytics_service
from services import stock as stock_service
from timeutil import parse_business_date

bp = Blueprint("analytics", __name__)


@bp.get("/api/analytics/sales/today")
def sales_today():
    return jsonify({"ok": True, **analytics_service.sales_today()})


@bp.get("/api/analytics/sales")
def sales_on_date():
    day = request.args.get("date")
    if not day:
        raise ApiError("date query parameter is required (YYYY-MM-DD)", 400, "missing_field")
    try:
        day = parse_business_date(day)
    except ValueError:
        raise ApiError("date must be YYYY-MM-DD", 400, "invalid_value") from None
    return jsonify({"ok": True, **analytics_service.sales_for_date(day)})


@bp.get("/api/analytics/sales/summary")
def sales_summary():
    return jsonify({"ok": True, **analytics_service.sales_summary()})


@bp.get("/api/analytics/sales/by-product")
def by_product():
    return jsonify({"ok": True, "products": analytics_service.product_sales()})


@bp.get("/api/analytics/stock")
def stock():
    return jsonify({"ok": True, "stock": stock_service.list_stock()})


@bp.get("/api/analytics/stock/low")
def stock_low():
    return jsonify({"ok": True, "stock": stock_service.list_stock(low_only=True)})
