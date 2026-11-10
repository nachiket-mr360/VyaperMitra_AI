from __future__ import annotations

from flask import Blueprint, jsonify, request

from services import memory as memory_service
from validate import require_json_object, require_str

bp = Blueprint("memory", __name__)


@bp.get("/api/memory")
def list_memory():
    layer = request.args.get("layer")
    if layer not in {None, "", "personal", "business"}:
        layer = None
    items = memory_service.list_memories(layer=layer or None)
    return jsonify({"ok": True, "memories": items}), 200


@bp.delete("/api/memory/<memory_id>")
def delete_memory(memory_id: str):
    return jsonify(memory_service.forget(memory_id)), 200


@bp.post("/api/memory")
def create_memory():
    body = require_json_object(request.get_json(silent=True))
    layer = require_str(body, "layer", max_len=20)
    key = require_str(body, "key", max_len=80)
    value = require_str(body, "value", max_len=200)
    if layer not in {"personal", "business"}:
        from errors import ApiError

        raise ApiError("layer must be personal or business", 400, "invalid_value")
    row = memory_service.upsert(layer, key, value, source="settings")
    return jsonify({"ok": True, "memory": row}), 200
