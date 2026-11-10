from __future__ import annotations

from typing import Any

from catalog import lexicon_key
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
    ids: dict[int, Any] = {}

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
    for row in list(exact) + list(aliases):
        ids[int(row["id"])] = row
    if ids:
        return list(ids.values())

    key = lexicon_key(normalized)
    if key:
        forms = {normalize_text(key)}
        from catalog import LEXICON

        for _lang, label in LEXICON[key]:
            forms.add(normalize_text(label))
        qmarks = ",".join("?" * len(forms))
        params = list(forms)
        lex_rows = conn.execute(
            f"SELECT * FROM products WHERE active = 1 AND normalized_name IN ({qmarks})",
            params,
        ).fetchall()
        lex_alias = conn.execute(
            f"""
            SELECT p.* FROM product_aliases a
            JOIN products p ON p.id = a.product_id
            WHERE p.active = 1 AND a.normalized_alias IN ({qmarks})
            """,
            params,
        ).fetchall()
        for row in list(lex_rows) + list(lex_alias):
            ids[int(row["id"])] = row
        if ids:
            return list(ids.values())

    token_keys = {lexicon_key(t) for t in normalized.split() if lexicon_key(t)}
    if len(token_keys) == 1:
        only = next(iter(token_keys))
        from catalog import LEXICON

        forms = {normalize_text(only)}
        for _lang, label in LEXICON[only]:
            forms.add(normalize_text(label))
        qmarks = ",".join("?" * len(forms))
        params = list(forms)
        lex_rows = conn.execute(
            f"SELECT * FROM products WHERE active = 1 AND normalized_name IN ({qmarks})",
            params,
        ).fetchall()
        lex_alias = conn.execute(
            f"""
            SELECT p.* FROM product_aliases a
            JOIN products p ON p.id = a.product_id
            WHERE p.active = 1 AND a.normalized_alias IN ({qmarks})
            """,
            params,
        ).fetchall()
        for row in list(lex_rows) + list(lex_alias):
            ids[int(row["id"])] = row
        if ids:
            return list(ids.values())

    if " " not in normalized:
        token_hits: dict[int, Any] = {}
        rows = conn.execute("SELECT * FROM products WHERE active = 1").fetchall()
        for row in rows:
            tokens = set(str(row["normalized_name"]).split())
            if normalized in tokens:
                token_hits[int(row["id"])] = row
        alias_rows = conn.execute(
            """
            SELECT p.*, a.normalized_alias AS match_alias
            FROM product_aliases a
            JOIN products p ON p.id = a.product_id
            WHERE p.active = 1
            """
        ).fetchall()
        for row in alias_rows:
            tokens = set(str(row["match_alias"]).split())
            if normalized in tokens:
                token_hits[int(row["id"])] = row
        if token_hits:
            return list(token_hits.values())

    return []


def _product_public(row: Any) -> dict[str, Any]:
    known = True
    if "stock_known" in row.keys():
        known = bool(row["stock_known"])
    stock = micro_to_units(int(row["current_stock"])) if known else None
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "unit": row["unit"],
        "current_stock": stock,
        "stock_known": known,
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
        return ResolveResult(product=None, candidates=[], unknown=True, ambiguous=False)
