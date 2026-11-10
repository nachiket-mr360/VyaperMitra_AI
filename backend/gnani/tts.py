"""Gnani Timbre REST TTS. Documented POST /api/v1/tts/inference only."""

from __future__ import annotations

import logging

import requests

from config import Config
from errors import ApiError

logger = logging.getLogger("vyaparmitra.gnani.tts")

TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"
LANG_MAP = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN", "mr": "mr-IN"}


def configured() -> bool:
    return bool((Config.GNANI_API_KEY or "").strip())


def synthesize(text: str, language: str) -> tuple[bytes, str]:
    if not text.strip():
        raise ApiError("Nothing to speak.", 400, "invalid_value")
    key = (Config.GNANI_API_KEY or "").strip()
    if not key:
        raise ApiError("Speech playback is not configured.", 503, "tts_not_configured")
    lang = LANG_MAP.get((language or "en").lower(), "en-IN")
    body = {
        "text": text.strip()[:2000],
        "voice": Config.GNANI_TTS_VOICE,
        "model": Config.GNANI_TTS_MODEL,
        "language": lang,
        "audio_config": {"container": "wav"},
    }
    try:
        res = requests.post(
            TTS_URL,
            json=body,
            headers={"X-API-Key-ID": key, "Content-Type": "application/json"},
            timeout=30,
        )
    except requests.Timeout as exc:
        raise ApiError("Speech playback timed out.", 504, "tts_timeout") from exc
    except requests.RequestException as exc:
        logger.warning("TTS network error type=%s", type(exc).__name__)
        raise ApiError("Speech playback is unavailable.", 502, "tts_unavailable") from exc
    if res.status_code in {401, 403}:
        raise ApiError("Speech playback rejected the API key.", 401, "tts_unauthorized")
    if res.status_code == 429:
        raise ApiError("Speech playback is rate limited.", 429, "tts_rate_limited")
    if res.status_code >= 400:
        logger.warning("TTS http=%s", res.status_code)
        raise ApiError("Speech playback failed.", 502, "tts_unavailable")
    ctype = (res.headers.get("Content-Type") or "").lower()
    data = res.content or b""
    if not data:
        raise ApiError("Speech playback returned no audio.", 502, "tts_unavailable")
    if "json" in ctype:
        raise ApiError("Speech playback returned no audio.", 502, "tts_unavailable")
    if "mpeg" in ctype or "mp3" in ctype:
        return data, "audio/mpeg"
    return data, "audio/wav"
