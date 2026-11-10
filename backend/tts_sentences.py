"""Speakable TTS chunks. Keep in sync with frontend/src/audio/ttsSentences.ts"""

from __future__ import annotations

import re

ABBREV = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "sr",
    "jr",
    "vs",
    "etc",
    "rs",
    "no",
    "nos",
    "kg",
    "g",
    "ml",
    "l",
    "ltd",
    "inc",
    "st",
    "nd",
    "rd",
    "th",
}

MIN_SHORT = 28
_ABBREV_RE = re.compile(r"([A-Za-z\u0900-\u097F\u0C80-\u0CFF]+)\.$")
_ENDERS = re.compile(r"[.!?।]")


def split_speakable(text: str) -> list[str]:
    raw = re.sub(r"\s+", " ", text or "").strip()
    if not raw:
        return []
    cuts: list[int] = []
    for m in _ENDERS.finditer(raw):
        idx = m.start()
        before = raw[: idx + 1]
        after = raw[idx + 1 :]
        if idx > 0 and raw[idx - 1].isdigit() and after[:1].isdigit():
            continue
        if raw[idx] == ".":
            am = _ABBREV_RE.search(before)
            if am and am.group(1).lower() in ABBREV:
                continue
            head = raw[:idx]
            if re.search(r"(?:^|[\s(])[A-Z]$", head):
                continue
        if not after.strip():
            cuts.append(idx + 1)
            continue
        if after[:1].isspace() or raw[idx] == "।":
            cuts.append(idx + 1)
    internal = [c for c in cuts if c < len(raw)]
    if not internal:
        return [raw]
    parts: list[str] = []
    start = 0
    for c in cuts:
        piece = raw[start:c].strip()
        if piece:
            parts.append(piece)
        start = c
    tail = raw[start:].strip()
    if tail:
        parts.append(tail)
    merged: list[str] = []
    for p in parts:
        last = merged[-1] if merged else ""
        last_complete = last.endswith((".", "!", "?", "।"))
        if merged and not last_complete and len(last) < MIN_SHORT:
            merged[-1] = f"{last} {p}"
        elif merged and not last_complete and len(p) < 12:
            merged[-1] = f"{last} {p}"
        else:
            merged.append(p)
    return merged or [raw]
