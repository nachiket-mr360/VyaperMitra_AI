"""Input vs reply language. Does not rewrite transcripts."""

from __future__ import annotations

import re
from typing import Any

SUPPORTED = ("en", "hi", "kn", "mr")
MODES = ("auto", "en", "hi", "kn", "mr")

_MR = re.compile(
    r"किती|झाली|एकूण|आजची|तुमची|विक्री|पदार्थ|मराठी|येते|तुला|आहात|आहेस|सकाळी|उद्या|वाजता|आठवण"
)
_TA = re.compile(r"[\u0B80-\u0BFF]")
_KN = re.compile(r"[\u0C80-\u0CFF]")
_DEV = re.compile(r"[\u0900-\u097F]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_input_language(text: str) -> str:
    raw = text or ""
    if _TA.search(raw):
        return "ta"
    if _KN.search(raw):
        return "kn"
    if _DEV.search(raw):
        return "mr" if _MR.search(raw) else "hi"
    if _LATIN.search(raw):
        return "en"
    return "en"


def language_confidence(text: str, detected: str) -> float:
    raw = (text or "").strip()
    if not raw:
        return 0.0
    if detected == "ta":
        return 0.95
    if _TA.search(raw) and (_KN.search(raw) or _DEV.search(raw)):
        return 0.35
    if detected in {"hi", "kn", "mr"}:
        return 0.85
    if len(raw) < 2:
        return 0.3
    return 0.7


def resolve_reply_language(
    transcript: str,
    *,
    mode: str | None,
    detected: str | None = None,
) -> tuple[str, str, float]:
    """Returns (reply_language, detected_input, confidence). Manual mode overrides detect."""
    det = detected or detect_input_language(transcript)
    conf = language_confidence(transcript, det)
    m = (mode or "auto").strip().lower()
    if m in SUPPORTED:
        return m, det, conf
    if det in SUPPORTED:
        return det, det, conf
    return "en", det, conf


def stick_reply_language(
    transcript: str,
    *,
    mode: str | None,
    session_lang: str | None = None,
    detected: str | None = None,
) -> tuple[str, str, float]:
    """Keep session language across short confirms; still honor a clear language switch."""
    lang, det, conf = resolve_reply_language(transcript, mode=mode, detected=detected)
    m = (mode or "auto").strip().lower()
    if m != "auto" or session_lang not in SUPPORTED:
        return lang, det, conf
    from intents.confirm_speech import classify_confirm_speech

    if classify_confirm_speech(transcript):
        return session_lang, det, conf
    words = (transcript or "").split()
    if det == "en" and session_lang != "en" and len(words) <= 6 and not _LATIN.search(transcript or ""):
        return session_lang, det, conf
    if det == "en" and session_lang != "en" and classify_confirm_speech(transcript or ""):
        return session_lang, det, conf
    return lang, det, conf


def tamil_limitation_message(reply_lang: str) -> str:
    lines = {
        "en": "Tamil speech is not supported yet. Please repeat in English, Hindi, Kannada, or Marathi.",
        "hi": "तमिल अभी समर्थित नहीं है। अंग्रेज़ी, हिंदी, कन्नड़ या मराठी में दोहराएँ।",
        "kn": "ತಮಿಳು ಇನ್ನೂ ಬೆಂಬಲಿತವಲ್ಲ. ಇಂಗ್ಲಿಷ್, ಹಿಂದಿ, ಕನ್ನಡ ಅಥವಾ ಮರಾಠಿಯಲ್ಲಿ ಹೇಳಿ.",
        "mr": "तमिळ अद्याप समर्थित नाही. इंग्रजी, हिंदी, कन्नड किंवा मराठीत पुन्हा सांगा.",
    }
    return lines.get(reply_lang, lines["en"])


def low_confidence_prompt(reply_lang: str) -> str:
    lines = {
        "en": "Which language should I use — English, Hindi, Kannada, or Marathi?",
        "hi": "किस भाषा में जवाब दूँ — अंग्रेज़ी, हिंदी, कन्नड़ या मराठी?",
        "kn": "ಯಾವ ಭಾಷೆ — ಇಂಗ್ಲಿಷ್, ಹಿಂದಿ, ಕನ್ನಡ ಅಥವಾ ಮರಾಠಿ?",
        "mr": "कोणती भाषा वापरू — इंग्रजी, हिंदी, कन्नड की मराठी?",
    }
    return lines.get(reply_lang, lines["en"])


def stt_language_for_mode(mode: str | None) -> str:
    m = (mode or "auto").strip().lower()
    return {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN", "mr": "mr-IN"}.get(m, "auto")


def normalize_mode(raw: Any) -> str:
    v = str(raw or "auto").strip().lower()
    return v if v in MODES else "auto"
