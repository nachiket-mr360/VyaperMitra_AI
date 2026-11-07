from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParseDraft:
    intent: str
    product_query: str | None
    quantity: float | None
    unit: str | None
    sale_amount: float | None
    missing: list[str] = field(default_factory=list)
    error_code: str | None = None
    message: str = ""


@dataclass
class ResolveResult:
    product: dict[str, Any] | None
    candidates: list[dict[str, Any]]
    unknown: bool
    ambiguous: bool
