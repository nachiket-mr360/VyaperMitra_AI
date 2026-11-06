"""INR as integer paise; quantities as integer micro-units (1e-6 of the product unit).

JSON still uses rupees and unit quantities. Persistence never uses binary float.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from errors import ApiError

RUPEE = Decimal("0.01")
MICRO = Decimal("0.000001")
PAISE_PER_RUPEE = 100
MICROS_PER_UNIT = 1_000_000


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ApiError(f"{field} must be a number", 400, "invalid_type")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except Exception as exc:
            raise ApiError(f"{field} must be a number", 400, "invalid_type") from exc
    raise ApiError(f"{field} must be a number", 400, "invalid_type")


def rupees_to_paise(value: Any, field: str = "amount") -> int:
    amount = _decimal(value, field).quantize(RUPEE, rounding=ROUND_HALF_UP)
    if amount < 0:
        raise ApiError(f"{field} cannot be negative", 400, "invalid_value")
    return int(amount * PAISE_PER_RUPEE)


def paise_to_rupees(paise: int) -> float:
    return float(Decimal(paise) / PAISE_PER_RUPEE)


def units_to_micro(value: Any, field: str = "quantity") -> int:
    amount = _decimal(value, field).quantize(MICRO, rounding=ROUND_HALF_UP)
    return int(amount * MICROS_PER_UNIT)


def micro_to_units(micro: int) -> float:
    return float(Decimal(micro) / MICROS_PER_UNIT)


def line_paise(quantity_micro: int, unit_price_paise: int) -> int:
    """line_total = round(qty * unit_price) using Decimal."""
    qty = Decimal(quantity_micro) / MICROS_PER_UNIT
    price = Decimal(unit_price_paise) / PAISE_PER_RUPEE
    return rupees_to_paise(qty * price, "line_total")


def unit_paise_from_line(quantity_micro: int, line_total_paise: int) -> int:
    if quantity_micro <= 0:
        raise ApiError("quantity must be greater than 0", 400, "invalid_value")
    qty = Decimal(quantity_micro) / MICROS_PER_UNIT
    total = Decimal(line_total_paise) / PAISE_PER_RUPEE
    return rupees_to_paise(total / qty, "unit_price")
