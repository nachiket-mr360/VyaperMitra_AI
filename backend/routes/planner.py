from __future__ import annotations

from flask import Blueprint, jsonify, request

from services import planner as planner_service
from validate import require_json_object, require_str

bp = Blueprint("planner", __name__)


@bp.get("/api/reminders/briefing")
def briefing():
    return jsonify({"ok": True, **planner_service.briefing()})


@bp.get("/api/reminders")
def list_reminders():
    status = request.args.get("status")
    return jsonify({"ok": True, "reminders": planner_service.list_reminders(status=status)})


@bp.post("/api/reminders")
def create_reminder():
    body = require_json_object(request.get_json(silent=True))
    title = require_str(body, "title", max_len=200)
    due_date = require_str(body, "due_date", max_len=16)
    due_time = body.get("due_time")
    if due_time is not None:
        due_time = str(due_time).strip() or None
    rec = str(body.get("recurrence") or "none")
    row = planner_service.create_reminder(
        title,
        due_date,
        due_time,
        rec,
        body.get("weekday"),
        body.get("month_day"),
        str(body.get("language") or "en"),
    )
    return jsonify({"ok": True, "reminder": row}), 201


@bp.patch("/api/reminders/<int:reminder_id>")
def patch_reminder(reminder_id: int):
    body = require_json_object(request.get_json(silent=True))
    row = planner_service.update_reminder(reminder_id, body)
    return jsonify({"ok": True, "reminder": row})


@bp.post("/api/reminders/<int:reminder_id>/complete")
def complete_reminder(reminder_id: int):
    row = planner_service.complete_reminder(reminder_id)
    return jsonify({"ok": True, "reminder": row})


@bp.delete("/api/reminders/<int:reminder_id>")
def delete_reminder(reminder_id: int):
    row = planner_service.delete_reminder(reminder_id)
    return jsonify({"ok": True, "reminder": row})


@bp.get("/api/notes")
def list_notes():
    q = request.args.get("q")
    return jsonify({"ok": True, "notes": planner_service.list_notes(query=q)})


@bp.post("/api/notes")
def create_note():
    body = require_json_object(request.get_json(silent=True))
    text = require_str(body, "body", max_len=2000)
    row = planner_service.create_note(text)
    return jsonify({"ok": True, "note": row}), 201


@bp.patch("/api/notes/<int:note_id>")
def patch_note(note_id: int):
    body = require_json_object(request.get_json(silent=True))
    text = require_str(body, "body", max_len=2000)
    row = planner_service.update_note(note_id, text)
    return jsonify({"ok": True, "note": row})


@bp.delete("/api/notes/<int:note_id>")
def delete_note(note_id: int):
    row = planner_service.delete_note(note_id)
    return jsonify({"ok": True, "note": row})
