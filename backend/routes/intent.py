from __future__ import annotations

from flask import Blueprint, jsonify, request

from intents.executor import cancel_action, confirm_action, process_transcript
from validate import require_json_object, require_str

bp = Blueprint("intent", __name__)


@bp.post("/api/intents/parse")
def parse_intent():
    body = require_json_object(request.get_json(silent=True))
    transcript = require_str(body, "transcript", max_len=4000)
    return jsonify(process_transcript(transcript)), 200


@bp.post("/api/intents/confirm")
def confirm_intent():
    body = require_json_object(request.get_json(silent=True))
    pending_id = require_str(body, "pending_id", max_len=80)
    return jsonify(confirm_action(pending_id)), 200


@bp.post("/api/intents/cancel")
def cancel_intent():
    body = require_json_object(request.get_json(silent=True))
    pending_id = require_str(body, "pending_id", max_len=80)
    return jsonify(cancel_action(pending_id)), 200
