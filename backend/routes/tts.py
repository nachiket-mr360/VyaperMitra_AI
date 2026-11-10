import logging
import time

from flask import Blueprint, request

from errors import ApiError
from gnani import tts as tts_client
from speak import detect_language

bp = Blueprint("tts", __name__)
logger = logging.getLogger("vyaparmitra.tts")


@bp.post("/api/tts")
def tts_route():
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ApiError("text is required", 400, "missing_field")
    language = body.get("language")
    if not isinstance(language, str) or not language.strip():
        language = detect_language(text)
    t0 = time.perf_counter()
    audio, ctype = tts_client.synthesize(text.strip(), language)
    ms = int((time.perf_counter() - t0) * 1000)
    logger.info("tts_ready ms=%s bytes=%s lang=%s", ms, len(audio or b""), language)
    return audio, 200, {
        "Content-Type": ctype,
        "Cache-Control": "no-store",
        "Server-Timing": f"gnani_tts;dur={ms}",
        "X-TTS-Ms": str(ms),
    }
