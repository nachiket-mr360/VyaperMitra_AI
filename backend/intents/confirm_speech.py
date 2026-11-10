"""Spoken yes/no for pending actions. Not an LLM. Does not execute anything."""

from __future__ import annotations

import re

from intents.unclear import is_unclear_transcript
from validate import normalize_text

_YES_EXACT = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "yup",
        "ok",
        "okay",
        "confirm",
        "confirmed",
        "go ahead",
        "do it",
        "proceed",
        "please do",
        "sure",
        "yes confirm",
        "yes confirm it",
        "yes please",
        "please confirm",
        "haan",
        "ha",
        "हां",
        "हाँ",
        "हां जी",
        "हाँ जी",
        "ठीक है",
        "करो",
        "कर दो",
        "पुष्टि कर दो",
        "रिकॉर्ड कर दो",
        "हाँ पुष्टि कर दो",
        "हां पुष्टि कर दो",
        "ಹೌದು",
        "ಸರಿ",
        "ಮಾಡಿ",
        "होय",
        "नक्की",
        "करा",
    }
)
_NO_EXACT = frozenset(
    {
        "no",
        "nope",
        "nah",
        "cancel",
        "cancel it",
        "don't",
        "dont",
        "do not",
        "don't do that",
        "dont do that",
        "stop",
        "never mind",
        "nevermind",
        "नहीं",
        "नही",
        "मत करो",
        "रद्द",
        "रद्द करो",
        "ಬೇಡ",
        "ಇಲ್ಲ",
        "ರದ್ದು",
        "नाही",
        "नको",
        "रद्द करा",
        "no cancel",
        "cancel that",
    }
)


_YES_RE = re.compile(
    r"हाँ|हां|\bhaan\b|\byes\b|\byeah\b|\byep\b|\bconfirm|\bokay\b|\bok\b|"
    r"पुष्टि|रिकॉर्ड कर|कर दो|\bgo ahead\b|\bdo it\b|\bproceed\b|"
    r"ಹೌದು|\bಸರಿ\b|ಮಾಡಿ|होय|नक्की|\bकरा\b",
    re.I,
)
_NO_RE = re.compile(
    r"\bno\b|\bnope\b|\bcancel\b|don't|\bdont\b|नहीं|नही|मत करो|रद्द|"
    r"ಬೇಡ|ಇಲ್ಲ|ರದ್ದು|नाही|नको|never mind|\bstop\b",
    re.I,
)
_QUERY_RE = re.compile(
    r"\?|कितना|कितनी|कितने|how much|\bstock\b|बताओ|tell me|what is|क्या है",
    re.I,
)


def classify_confirm_speech(transcript: str) -> str | None:
    raw = (transcript or "").strip()
    if not raw or is_unclear_transcript(raw):
        return None
    n = normalize_text(raw).replace("'", "")
    compact = re.sub(r"[^\w\s\u0900-\u097F\u0C80-\u0CFF]+", " ", n)
    compact = re.sub(r"[\u0964\u0965।.!?]+", " ", compact)
    compact = re.sub(r"\s+", " ", compact).strip()
    if not compact:
        return None
    if compact in _NO_EXACT:
        return "no"
    if compact in _YES_EXACT:
        return "yes"
    if len(compact.split()) > 24:
        return None
    if _NO_RE.search(compact) and not re.search(r"पुष्टि|confirm|रिकॉर्ड कर", compact, re.I):
        return "no"
    if _YES_RE.search(compact):
        if _QUERY_RE.search(compact) and not re.search(r"पुष्टि|confirm|रिकॉर्ड कर|कर दो", compact, re.I):
            return None
        if _NO_RE.search(compact):
            return None
        return "yes"
    return None
