"""Request validation. Never trust client numbers."""

from __future__ import annotations

import re
from typing import Any

from errors import ApiError

_WS = re.compile(r"\s+")

ALLOWED_UNITS = frozenset(
    {
        "kg",
        "g",
        "l",
        "ml",
        "pcs",
        "pc",
        "packet",
        "pkts",
        "dozen",
        "bag",
        "box",
        "bunch",
        "piece",
        "pieces",
    }
)
PROTECTED_PRODUCT_FIELDS = frozenset(
    {
        "id",
        "current_stock",
        "normalized_name",
        "created_at",
        "updated_at",
        "low_stock",
    }
)


def normalize_text(value: str) -> str:
    return _WS.sub(" ", value.strip()).lower()


def require_str(body: dict[str, Any], field: str, *, max_len: int = 200) -> str:
    if field not in body or body[field] is None:
        raise ApiError(f"Missing field: {field}", 400, "missing_field")
    if not isinstance(body[field], str):
        raise ApiError(f"{field} must be a string", 400, "invalid_type")
    text = body[field].strip()
    if not text:
        raise ApiError(f"{field} cannot be empty", 400, "invalid_value")
    if len(text) > max_len:
        raise ApiError(f"{field} is too long", 400, "invalid_value")
    return text


def optional_str(body: dict[str, Any], field: str, *, max_len: int = 500) -> str | None:
    if field not in body or body[field] is None:
        return None
    if not isinstance(body[field], str):
        raise ApiError(f"{field} must be a string", 400, "invalid_type")
    text = body[field].strip()
    if len(text) > max_len:
        raise ApiError(f"{field} is too long", 400, "invalid_value")
    return text or None


def require_number(body: dict[str, Any], field: str) -> float:
    if field not in body or body[field] is None:
        raise ApiError(f"Missing field: {field}", 400, "missing_field")
    value = body[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(f"{field} must be a number", 400, "invalid_type")
    return float(value)


def optional_number(body: dict[str, Any], field: str) -> float | None:
    if field not in body or body[field] is None:
        return None
    value = body[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(f"{field} must be a number", 400, "invalid_type")
    return float(value)


def require_positive(body: dict[str, Any], field: str) -> float:
    value = require_number(body, field)
    if value <= 0:
        raise ApiError(f"{field} must be greater than 0", 400, "invalid_value")
    return value


def require_non_negative(body: dict[str, Any], field: str) -> float:
    value = require_number(body, field)
    if value < 0:
        raise ApiError(f"{field} cannot be negative", 400, "invalid_value")
    return value


def require_int_id(value: Any, name: str = "id") -> int:
    try:
        ident = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"Invalid {name}", 400, "invalid_type") from None
    if ident < 1:
        raise ApiError(f"Invalid {name}", 400, "invalid_value")
    return ident


def require_json_object(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ApiError("JSON object required", 400, "invalid_type")
    return data


def require_unit(value: str) -> str:
    unit = value.strip().lower()
    if unit not in ALLOWED_UNITS:
        raise ApiError(
            "unit must be one of: " + ", ".join(sorted(ALLOWED_UNITS)),
            400,
            "invalid_value",
        )
    return unit


def reject_protected_product_fields(body: dict[str, Any]) -> None:
    bad = sorted(PROTECTED_PRODUCT_FIELDS.intersection(body.keys()))
    if bad:
        raise ApiError(
            "Cannot update protected fields: " + ", ".join(bad),
            400,
            "protected_field",
        )
