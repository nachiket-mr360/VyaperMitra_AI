"""Phase 1 health check against the isolated test database."""

from __future__ import annotations


def test_health_ok(client):
    response = client.get("/api/health")
    data = response.get_json()
    assert response.status_code == 200
    assert data["ok"] is True
    assert data["app"] == "VyaparMitra"
    assert data["phase"] == 3
    assert data["timezone"] == "Asia/Kolkata"
    assert data["database"]["connected"] is True
    assert data["gnani"]["integration"] == "prisma_stt"
    assert "GNANI_API_KEY" not in str(data)


def test_unknown_route_json_error(client):
    response = client.get("/api/does-not-exist")
    data = response.get_json()
    assert response.status_code == 404
    assert data["ok"] is False
    assert "Traceback" not in str(data)


def test_health_security_headers(client):
    response = client.get("/api/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
