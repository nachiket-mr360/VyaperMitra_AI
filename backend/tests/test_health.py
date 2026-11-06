"""Phase 1 API tests. Run from backend/: python -m pytest tests -q"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: E402


def test_health_ok():
    client = app.test_client()
    response = client.get("/api/health")
    data = response.get_json()
    assert response.status_code == 200
    assert data["ok"] is True
    assert data["app"] == "VyaparMitra"
    assert data["phase"] == 1
    assert data["timezone"] == "Asia/Kolkata"
    assert data["database"]["connected"] is True
    assert data["gnani"]["integration"] == "not_started"
    assert "GNANI_API_KEY" not in json.dumps(data)
    assert "server_time" in data


def test_unknown_route_json_error():
    client = app.test_client()
    response = client.get("/api/does-not-exist")
    data = response.get_json()
    assert response.status_code == 404
    assert data["ok"] is False
    assert "error" in data
    assert "message" in data["error"]
    assert "Traceback" not in json.dumps(data)


def test_health_security_headers():
    client = app.test_client()
    response = client.get("/api/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
