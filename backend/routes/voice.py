from __future__ import annotations

from flask import Blueprint, jsonify, request

from errors import ApiError
from gnani.audio import validate_audio
from gnani.stt import transcribe

bp = Blueprint("voice", __name__)


@bp.post("/api/voice/transcribe")
def transcribe_audio():
    if "audio" not in request.files:
        raise ApiError("Missing audio file.", 400, "missing_audio")
    upload = request.files["audio"]
    filename = upload.filename or ""
    data = upload.read()
    if data is None:
        data = b""
    clip = validate_audio(
        data=data,
        filename=filename,
        content_type=upload.mimetype,
    )
    language = request.form.get("language") or request.args.get("language") or "auto"
    result = transcribe(clip, language)
    return jsonify(result), 200
