"""Rule memory commands and stable-fact extraction. Not an LLM. Does not write SQLite."""

from __future__ import annotations

import re
from typing import Any

from validate import normalize_text

_LANG = {
    "english": "en",
    "hindi": "hi",
    "kannada": "kn",
    "marathi": "mr",
    "अंग्रेज़ी": "en",
    "हिंदी": "hi",
    "हिन्दी": "hi",
    "ಕನ್ನಡ": "kn",
    "मराठी": "mr",
}

_CASUAL = (
    "today was",
    "just saying",
    "maybe later",
    "i think i will",
    "weather",
    "hungry",
)
_TX = (
    "i purchased",
    "i sold",
    "customer bought",
    "record sale",
    "add stock",
    "kg of",
    "rupees",
)


def _lang_token(text: str) -> str | None:
    n = normalize_text(text)
    raw = text
    for name, code in _LANG.items():
        if name in n or name in raw:
            return code
    return None


def parse_memory_command(transcript: str) -> dict[str, Any] | None:
    raw = (transcript or "").strip()
    n = normalize_text(raw)
    if not n:
        return None
    if re.search(r"don'?t remember this conversation|forget this conversation|इस बातचीत को मत याद", n):
        return {"op": "skip_extract"}
    if re.search(r"forget everything|forget all (about )?me|मुझसे जुड़ी सब यादें भूल", n):
        return {"op": "forget_all"}
    if re.search(r"what do you (remember|know) about my shop|मेरी दुकान के बारे में क्या", n) or "shop" in n and "remember" in n:
        if "about me" not in n:
            return {"op": "list", "layer": "business"}
    if re.search(r"what do you remember|what do you know about me|तुम्हें मेरे बारे में", n):
        return {"op": "list", "layer": "personal"}
    m = re.search(
        r"(?:change|update|set) (?:my )?preferred language (?:to )?([a-zA-Z\u0900-\u097F\u0C80-\u0CFF]+)",
        n,
    )
    if m:
        code = _lang_token(m.group(1)) or _lang_token(raw)
        if code:
            return {"op": "upsert", "layer": "personal", "key": "preferred_language", "value": code, "explicit": True}
    if re.search(r"forget (my )?(old )?language preference|भाषा पसंद भूल", n):
        return {"op": "forget_key", "layer": "personal", "key": "preferred_language"}
    if n.startswith("remember that") or n.startswith("remember "):
        rest = re.sub(r"^remember (that )?", "", n).strip()
        extracted = extract_stable_facts(rest) or extract_stable_facts(raw)
        if extracted:
            extracted[0]["explicit"] = True
            extracted[0]["op"] = "upsert"
            return extracted[0]
        if rest:
            return None
    return None


def extract_stable_facts(transcript: str) -> list[dict[str, Any]]:
    raw = (transcript or "").strip()
    n = normalize_text(raw)
    if not n or any(c in n for c in _CASUAL):
        return []
    if any(t in n for t in _TX) and "remember" not in n:
        return []
    found: list[dict[str, Any]] = []
    m = re.search(r"(?:my name is|i am|i'm|मेरा नाम)\s+([A-Za-z\u0900-\u097F]{2,40})", raw, re.I)
    if m and m.group(1).lower() not in {"a", "the", "going"}:
        found.append({"layer": "personal", "key": "preferred_name", "value": m.group(1).strip().rstrip("."), "explicit": False})
    lang = None
    if re.search(r"prefer (speaking in |to speak )?|preferred language|पसंद.*मराठी|मराठी पसंद", n) or "i prefer" in n:
        lang = _lang_token(raw) or _lang_token(n)
        if lang:
            found.append({"layer": "personal", "key": "preferred_language", "value": lang, "explicit": False})
    if re.search(r"short answers|keep it short|संक्षेप|छोटे जवाब", n):
        found.append({"layer": "personal", "key": "explanation_style", "value": "short", "explicit": False})
    m = re.search(
        r"(?:my shop is called|shop is called|shop name is|दुकान का नाम)\s+(.+)",
        raw,
        re.I,
    )
    if m:
        name = m.group(1).strip().rstrip(".")
        if 2 <= len(name) <= 80 and not _looks_tx(name):
            found.append({"layer": "business", "key": "shop_name", "value": name, "explicit": False})
    if re.search(r"grocery shop|kirana|ग्रॉसरी|किराना", n):
        found.append({"layer": "business", "key": "shop_type", "value": "grocery", "explicit": False})
    m = re.search(
        r"(?:regular supplier is|supplier is|सप्लायर)\s+([A-Za-z0-9][A-Za-z0-9 .'\-]{1,60})",
        raw,
        re.I,
    )
    if not m:
        m = re.search(
            r"([A-Za-z0-9][A-Za-z0-9 .'\-]{1,60})\s+is my regular supplier",
            raw,
            re.I,
        )
    if m:
        found.append(
            {
                "layer": "business",
                "key": "preferred_supplier",
                "value": m.group(1).strip().rstrip("."),
                "explicit": False,
            }
        )
    return found


def _looks_tx(text: str) -> bool:
    n = normalize_text(text)
    return any(t in n for t in _TX) or bool(re.search(r"\d+\s*(kg|g|rs)", n))


def classify_candidate(transcript: str, fact: dict[str, Any]) -> str:
    if fact.get("explicit"):
        return "stable"
    n = normalize_text(transcript)
    if any(t in n for t in _TX):
        return "transactional"
    if any(c in n for c in _CASUAL):
        return "temporary"
    if fact["key"] in {"preferred_language", "preferred_name", "shop_name", "shop_type", "preferred_supplier", "explanation_style"}:
        return "stable"
    return "uncertain"
