"""Curated multilingual aliases. Flask-only; Gemini must not write this."""

from __future__ import annotations

from validate import normalize_text

# canonical_key -> list of (language, display)
# Keys are English grocery names used as products.normalized_name when created from the lexicon.
LEXICON: dict[str, list[tuple[str, str]]] = {
    "rice": [
        ("en", "Rice"),
        ("en", "Chawal"),
        ("hi", "चावल"),
        ("hi", "राइस"),
        ("en", "Akki"),
        ("kn", "ಅಕ್ಕಿ"),
        ("en", "Tandul"),
        ("mr", "तांदूळ"),
    ],
    "milk": [
        ("en", "Milk"),
        ("hi", "दूध"),
        ("kn", "ಹಾಲು"),
        ("mr", "दूध"),
        ("en", "Doodh"),
        ("en", "Haalu"),
    ],
    "sugar": [
        ("en", "Sugar"),
        ("hi", "चीनी"),
        ("kn", "ಸಕ್ಕರೆ"),
        ("mr", "साखर"),
        ("en", "Cheeni"),
        ("en", "Sakkare"),
    ],
    "wheat": [
        ("en", "Wheat"),
        ("hi", "गेहूं"),
        ("kn", "ಗೋಧಿ"),
        ("mr", "गहू"),
    ],
    "atta": [
        ("en", "Atta"),
        ("en", "Wheat flour"),
        ("hi", "आटा"),
        ("kn", "ಹಿಟ್ಟು"),
        ("mr", "पीठ"),
    ],
    "oil": [
        ("en", "Oil"),
        ("hi", "तेल"),
        ("kn", "ಎಣ್ಣೆ"),
        ("mr", "तेल"),
    ],
    "salt": [
        ("en", "Salt"),
        ("hi", "नमक"),
        ("kn", "ಉಪ್ಪು"),
        ("mr", "मीठ"),
    ],
    "tea": [
        ("en", "Tea"),
        ("hi", "चाय"),
        ("kn", "ಚಹಾ"),
        ("mr", "चहा"),
    ],
    "onion": [
        ("en", "Onion"),
        ("hi", "प्याज"),
        ("kn", "ಈರುಳ್ಳಿ"),
        ("mr", "कांदा"),
    ],
    "potato": [
        ("en", "Potato"),
        ("hi", "आलू"),
        ("kn", "ಆಲೂಗಡ್ಡೆ"),
        ("mr", "बटाटा"),
    ],
    "dal": [
        ("en", "Dal"),
        ("en", "Toor dal"),
        ("hi", "दाल"),
        ("kn", "ಬೇಳೆ"),
        ("mr", "डाळ"),
    ],
}

_ALIAS_TO_KEY: dict[str, str] = {}
for _key, _forms in LEXICON.items():
    _ALIAS_TO_KEY[normalize_text(_key)] = _key
    for _lang, _label in _forms:
        _ALIAS_TO_KEY[normalize_text(_label)] = _key


def lexicon_key(query: str | None) -> str | None:
    if not query:
        return None
    return _ALIAS_TO_KEY.get(normalize_text(query))


def canonical_name(query: str) -> str:
    key = lexicon_key(query)
    if key:
        return key.title() if key != "atta" else "Atta"
    return query.strip()


def suggested_aliases(query: str) -> list[dict[str, str]]:
    key = lexicon_key(query)
    if not key:
        spoken = query.strip()
        if not spoken:
            return []
        return [{"alias": spoken, "language": "und", "normalized": normalize_text(spoken)}]
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for lang, label in LEXICON[key]:
        n = normalize_text(label)
        if n in seen:
            continue
        seen.add(n)
        out.append({"alias": label, "language": lang, "normalized": n})
    return out


def attach_suggested_aliases(conn, product_id: int, query: str) -> None:
    from timeutil import now_business

    attach_alias_rows(conn, product_id, suggested_aliases(query), now_business().isoformat())


def seed_aliases_for_existing(conn) -> None:
    """Attach curated aliases to matching products. Does not create products or change stock."""
    from timeutil import now_business

    now = now_business().isoformat()
    rows = conn.execute("SELECT id, name, normalized_name FROM products WHERE active = 1").fetchall()
    for row in rows:
        key = lexicon_key(row["normalized_name"]) or lexicon_key(row["name"])
        if not key:
            continue
        attach_alias_rows(conn, int(row["id"]), suggested_aliases(key), now)


def attach_alias_rows(conn, product_id: int, aliases: list[dict[str, str]], now: str) -> None:
    for item in aliases:
        n = item["normalized"]
        name_hit = conn.execute(
            "SELECT id FROM products WHERE normalized_name = ? AND id != ?",
            (n, product_id),
        ).fetchone()
        if name_hit:
            continue
        existing = conn.execute(
            "SELECT product_id FROM product_aliases WHERE normalized_alias = ?",
            (n,),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """
            INSERT INTO product_aliases (product_id, alias, normalized_alias, language, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (product_id, item["alias"], n, item["language"], now),
        )
