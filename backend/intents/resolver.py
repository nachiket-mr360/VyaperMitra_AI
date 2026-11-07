from __future__ import annotations

from typing import Any

from db import atomic_connection
from intents.schemas import ResolveResult
from money import micro_to_units
from validate import normalize_text

_EN_EDGE_CONNECTORS = frozenset(
    {"at", "for", "of", "is", "was", "the", "a", "an", "to", "and"}
)


def _trim_query(normalized: str) -> str:
    tokens = [t for t in normalized.split() if t]
    while tokens and tokens[0] in _EN_EDGE_CONNECTORS:
        tokens.pop(0)
    while tokens and tokens[-1] in _EN_EDGE_CONNECTORS:
        tokens.pop()
    return " ".join(tokens)


def _catalog_match(conn, normalized: str) -> list:
    if not normalized:
        return []
    exact = conn.execute(
        "SELECT * FROM products WHERE normalized_name = ? AND active = 1",
        (normalized,),
    ).fetchall()
    aliases = conn.execute(
        """
        SELECT p.* FROM product_aliases a
        JOIN products p ON p.id = a.product_id
        WHERE a.normalized_alias = ? AND p.active = 1
        """,
        (normalized,),
    ).fetchall()
    ids: dict[int, Any] = {}
    for row in list(exact) + list(aliases):
        ids[int(row["id"])] = row
    if ids:
        return list(ids.values())
    rows = conn.execute(
        "SELECT * FROM products WHERE active = 1"
    ).fetchall()
    alias_rows = conn.execute(
        """
        SELECT p.*, a.normalized_alias AS match_alias
        FROM product_aliases a
        JOIN products p ON p.id = a.product_id
        WHERE p.active = 1
        """
    ).fetchall()
    padded = f" {normalized} "
    scored: dict[int, tuple[int, Any]] = {}
    for row in rows:
        name = str(row["normalized_name"])
        if f" {name} " in padded or padded.strip() == name:
            scored[int(row["id"])] = (len(name), row)
    for row in alias_rows:
        alias = str(row["match_alias"])
        if f" {alias} " in padded or padded.strip() == alias:
            pid = int(row["id"])
            prev = scored.get(pid)
            if prev is None or len(alias) > prev[0]:
                scored[pid] = (len(alias), row)
    q_tokens = set(normalized.split())
    if not scored and q_tokens:
        token_hits: dict[int, tuple[int, Any]] = {}
        for row in rows:
            name_tokens = set(str(row["normalized_name"]).split())
            if q_tokens <= name_tokens:
                token_hits[int(row["id"])] = (len(q_tokens), row)
        for row in alias_rows:
            alias_tokens = set(str(row["match_alias"]).split())
            if q_tokens <= alias_tokens:
                pid = int(row["id"])
                prev = token_hits.get(pid)
                if prev is None or len(q_tokens) > prev[0]:
                    token_hits[pid] = (len(q_tokens), row)
        if len(token_hits) == 1:
            scored = token_hits
    if not scored:
        return []
    best = max(s[0] for s in scored.values())
    return [row for length, row in scored.values() if length == best]


def _product_public(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "unit": row["unit"],
        "current_stock": micro_to_units(int(row["current_stock"])),
        "active": bool(row["active"]),
    }


def resolve_product(query: str | None) -> ResolveResult:
    if not query:
        return ResolveResult(product=None, candidates=[], unknown=True, ambiguous=False)
    normalized = _trim_query(normalize_text(query))
    with atomic_connection(immediate=False) as conn:
        hits = _catalog_match(conn, normalized)
        if len(hits) == 1:
            return ResolveResult(
                product=_product_public(hits[0]),
                candidates=[],
                unknown=False,
                ambiguous=False,
            )
        if len(hits) > 1:
            return ResolveResult(
                product=None,
                candidates=[_product_public(h) for h in hits],
                unknown=False,
                ambiguous=True,
            )
        like = f"%{normalized}%"
        fuzzy = conn.execute(
            """
            SELECT * FROM products
            WHERE active = 1 AND (
                normalized_name LIKE ? OR id IN (
                    SELECT product_id FROM product_aliases WHERE normalized_alias LIKE ?
                )
            )
            """,
            (like, like),
        ).fetchall()
        if len(fuzzy) == 1:
            return ResolveResult(
                product=_product_public(fuzzy[0]),
                candidates=[],
                unknown=False,
                ambiguous=False,
            )
        if len(fuzzy) > 1:
            return ResolveResult(
                product=None,
                candidates=[_product_public(h) for h in fuzzy],
                unknown=False,
                ambiguous=True,
            )
        return ResolveResult(product=None, candidates=[], unknown=True, ambiguous=False)
