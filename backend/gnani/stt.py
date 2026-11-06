"""Gnani Prisma V3 speech-to-text. One request per user action; no credit-burning retries."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from config import Config
from errors import ApiError
from gnani.audio import AudioClip

logger = logging.getLogger("vyaparmitra.gnani.stt")

LANGUAGE_MAP = {
    "auto": "indic-auto",
    "indic-auto": "indic-auto",
    "kn-in": "kn-IN",
    "hi-in": "hi-IN",
    "en-in": "en-IN",
    "mr-in": "mr-IN",
}

ALLOWED_UI_LANGUAGES = frozenset({"auto", "kn-IN", "hi-IN", "en-IN", "mr-IN"})


def resolve_language(raw: str | None) -> str:
    value = (raw or "auto").strip()
    key = value.lower()
    if key in LANGUAGE_MAP:
        return LANGUAGE_MAP[key]
    raise ApiError(
        "language must be auto, kn-IN, hi-IN, en-IN, or mr-IN.",
        400,
        "invalid_value",
    )


def _require_key() -> str:
    key = (Config.GNANI_API_KEY or "").strip()
    if not key:
        raise ApiError(
            "Speech recognition is not configured. Set GNANI_API_KEY on the server.",
            503,
            "gnani_not_configured",
        )
    return key


def _map_status(status: int) -> ApiError:
    if status in {401, 403}:
        return ApiError("Speech service rejected the API key.", 401, "gnani_unauthorized")
    if status == 402:
        return ApiError("Speech service credits are insufficient.", 402, "gnani_credits")
    if status == 429:
        return ApiError("Speech service is rate limited. Try again later.", 429, "gnani_rate_limited")
    if status >= 500:
        return ApiError("Speech service is unavailable.", 502, "gnani_unavailable")
    return ApiError("Speech service request failed.", 502, "gnani_unavailable")


def transcribe(clip: AudioClip, language: str) -> dict[str, Any]:
    api_key = _require_key()
    language_code = resolve_language(language)
    url = Config.GNANI_STT_URL
    model = Config.GNANI_STT_MODEL
    timeout = Config.GNANI_STT_TIMEOUT

    headers = {"X-API-Key-ID": api_key}
    files = {
        "audio_file": (clip.filename, clip.data, "application/octet-stream"),
    }
    data = {
        "model": model,
        "language_code": language_code,
    }

    started = time.perf_counter()
    try:
        response = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)
    except requests.Timeout as exc:
        logger.warning("Gnani STT timeout url_host_only")
        raise ApiError("Speech service timed out.", 504, "gnani_timeout") from exc
    except requests.RequestException as exc:
        logger.warning("Gnani STT connection error: %s", type(exc).__name__)
        raise ApiError("Could not reach the speech service.", 502, "gnani_unavailable") from exc

    latency = round(time.perf_counter() - started, 3)
    request_id = response.headers.get("X-Request-ID") or response.headers.get("x-request-id")
    logger.info(
        "Gnani STT status=%s latency_s=%s request_id=%s bytes=%s",
        response.status_code,
        latency,
        request_id or "none",
        len(clip.data),
    )

    if response.status_code >= 400:
        body_lower = (response.text or "").lower()
        if response.status_code == 402 or "insufficient" in body_lower and "credit" in body_lower:
            raise ApiError("Speech service credits are insufficient.", 402, "gnani_credits")
        raise _map_status(response.status_code)

    try:
        payload = response.json()
    except ValueError as exc:
        raise ApiError("Speech service returned an unreadable response.", 502, "malformed_upstream") from exc

    if not isinstance(payload, dict):
        raise ApiError("Speech service returned an unreadable response.", 502, "malformed_upstream")

    if payload.get("success") is False:
        raise ApiError("Speech service could not transcribe the audio.", 502, "gnani_unavailable")

    transcript = payload.get("transcript")
    if transcript is None:
        raise ApiError("Speech service returned an unreadable response.", 502, "malformed_upstream")
    if not isinstance(transcript, str) or not transcript.strip():
        raise ApiError("No speech was recognised.", 422, "empty_transcript")

    detected = payload.get("detected_language_code") or payload.get("detected_language")
    if detected is not None and not isinstance(detected, str):
        detected = None

    rid = payload.get("request_id") or request_id
    used_model = payload.get("model") or model

    usage = payload.get("usage") or payload.get("credits") or response.headers.get("X-Credits-Remaining")
    if usage is not None:
        logger.info("Gnani STT usage_hint=%s request_id=%s", usage, rid)

    return {
        "ok": True,
        "success": True,
        "transcript": transcript.strip(),
        "detected_language": detected,
        "model": used_model,
        "request_id": rid,
        "processing_time": latency,
        "language_sent": language_code,
    }
