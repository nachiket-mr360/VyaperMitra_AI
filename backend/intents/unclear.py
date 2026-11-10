"""Unclear / noisy speech recovery. Does not execute shop actions."""

from __future__ import annotations

import re

from validate import normalize_text

_FILLER = frozenset(
    {
        "hmm",
        "uh",
        "um",
        "ah",
        "er",
        "huh",
        "mm",
        "mmm",
        "noise",
        "music",
        "आ",
        "अह",
        "हम्म",
        "ಹ್ಮ್",
        "अं",
    }
)

_REPEAT = {
    "en": "I couldn't hear that clearly. Could you repeat it?",
    "hi": "साफ़ नहीं सुना। कृपया एक बार फिर कहें।",
    "kn": "ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ.",
    "mr": "स्पष्ट ऐकू आले नाही. कृपया पुन्हा सांगा.",
}

_NOISE = {
    "en": "There is some background noise. Please say that once again.",
    "hi": "आस-पास शोर है। कृपया एक बार फिर बोलें।",
    "kn": "ಸುತ್ತಲೂ ಶಬ್ದವಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಹೇಳಿ.",
    "mr": "आजूबाजूला गोंगाट आहे. कृपया पुन्हा सांगा.",
}


def is_unclear_transcript(transcript: str) -> bool:
    raw = (transcript or "").strip()
    if not raw:
        return True
    n = normalize_text(raw)
    compact = re.sub(r"[^\w\s\u0900-\u097F\u0C80-\u0CFF]+", " ", n)
    compact = re.sub(r"\s+", " ", compact).strip()
    if not compact:
        return True
    if re.search(r"\d", compact):
        return False
    if compact in _FILLER:
        return True
    letters = re.sub(r"\s+", "", compact)
    if len(letters) < 1:
        return True
    return False


def recovery_message(lang: str, *, noisy: bool = False) -> str:
    key = lang if lang in _REPEAT else "en"
    return (_NOISE if noisy else _REPEAT)[key]
