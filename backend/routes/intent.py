from __future__ import annotations

from flask import Blueprint, jsonify, request

from intents.executor import cancel_action, confirm_action, process_transcript
from validate import require_json_object, require_str

bp = Blueprint("intent", __name__)


@bp.post("/api/intents/parse")
def parse_intent():
    body = require_json_object(request.get_json(silent=True))
    transcript = require_str(body, "transcript", max_len=4000)
    session_id = body.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        session_id = None
    else:
        session_id = (session_id or "").strip() or None
    language_mode = body.get("language_mode")
    if language_mode is not None and not isinstance(language_mode, str):
        language_mode = None
    return jsonify(process_transcript(transcript, session_id=session_id, language_mode=language_mode)), 200


@bp.post("/api/intents/confirm")
def confirm_intent():
    body = require_json_object(request.get_json(silent=True))
    pending_id = require_str(body, "pending_id", max_len=80)
    session_id = body.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        session_id = None
    else:
        session_id = (session_id or "").strip() or None
    return jsonify(confirm_action(pending_id, session_id=session_id)), 200


@bp.post("/api/intents/cancel")
def cancel_intent():
    body = require_json_object(request.get_json(silent=True))
    pending_id = require_str(body, "pending_id", max_len=80)
    return jsonify(cancel_action(pending_id)), 200
