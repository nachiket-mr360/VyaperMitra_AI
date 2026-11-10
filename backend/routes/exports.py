from __future__ import annotations

from flask import Blueprint, Response, request

from errors import ApiError
from services import exports as export_service
from timeutil import parse_business_date

bp = Blueprint("exports", __name__)


def _csv_response(body: bytes, filename: str) -> Response:
    resp = Response(body, mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def _dates():
    day = request.args.get("date")
    date_from = request.args.get("from")
    date_to = request.args.get("to")
    for label, value in (("date", day), ("from", date_from), ("to", date_to)):
        if value:
            try:
                parse_business_date(value)
            except ValueError as exc:
                raise ApiError(f"{label} must be YYYY-MM-DD", 400, "invalid_value") from exc
    return day, date_from, date_to


@bp.get("/api/exports/sales.csv")
def export_sales():
    day, date_from, date_to = _dates()
    body, name = export_service.sales_csv(on_date=day, date_from=date_from, date_to=date_to)
    return _csv_response(body, name)


@bp.get("/api/exports/inventory.csv")
def export_inventory():
    body, name = export_service.inventory_csv()
    return _csv_response(body, name)


@bp.get("/api/exports/analytics.csv")
def export_analytics():
    _, date_from, date_to = _dates()
    body, name = export_service.analytics_csv(date_from=date_from, date_to=date_to)
    return _csv_response(body, name)
