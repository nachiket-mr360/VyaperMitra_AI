from __future__ import annotations


def _rice(client, stock: float = 50):
    res = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "opening_stock": stock},
    )
    assert res.status_code == 201
    pid = res.get_json()["product"]["id"]
    client.post(f"/api/products/{pid}/aliases", json={"alias": "चावल", "language": "hi"})
    client.post(f"/api/products/{pid}/aliases", json={"alias": "ಅಕ್ಕಿ", "language": "kn"})
    client.post(f"/api/products/{pid}/aliases", json={"alias": "तांदूळ", "language": "mr"})
    return pid


def _parse(client, text: str, session_id: str = "pipe-1"):
    return client.post("/api/intents/parse", json={"transcript": text, "session_id": session_id}).get_json()


def test_sale_commit_analytics_correct_cancel(client):
    _rice(client, 10)
    sid = "core-session"
    data = _parse(client, "आज एक ग्राहक ने एक किलो चावल 50 रुपये में लिया।", sid)
    assert data["intent"] == "record_sale"
    assert data["executed"] is True
    assert data["needs_confirmation"] is False
    sale = data["result"]["sale"]
    assert sale["total_amount"] == 50
    bills = client.get("/api/sales").get_json()["sales"]
    assert len(bills) == 1
    today = client.get("/api/analytics/sales/today").get_json()
    assert today["total_amount"] == 50
    assert today["transactions"] == 1
    dash = client.get("/api/analytics/dashboard").get_json()
    assert dash["today"]["total_amount"] == 50

    corr = _parse(client, "Change that to ₹60.", sid)
    assert corr["intent"] == "correct_sale"
    assert corr["needs_confirmation"] is True
    done = client.post(
        "/api/intents/confirm",
        json={"pending_id": corr["pending_id"], "session_id": sid},
    ).get_json()
    assert done["executed"] is True
    bills = client.get("/api/sales").get_json()["sales"]
    assert len(bills) == 1
    today = client.get("/api/analytics/sales/today").get_json()
    assert today["total_amount"] == 60

    cancel = _parse(client, "No, remove that sale.", sid)
    assert cancel["intent"] == "cancel_sale"
    assert cancel["needs_confirmation"] is True
    client.post(
        "/api/intents/confirm",
        json={"pending_id": cancel["pending_id"], "session_id": sid},
    )
    today = client.get("/api/analytics/sales/today").get_json()
    assert today["total_amount"] == 0
    stock = client.get("/api/products").get_json()["products"][0]["current_stock"]
    assert stock == 10


def test_duplicate_speech_does_not_double_sale(client):
    _rice(client, 10)
    sid = "dup-session"
    a = _parse(client, "I sold 1 kg of rice for 50 rupees", sid)
    b = _parse(client, "I sold 1 kg of rice for 50 rupees", sid)
    assert a["executed"] and b["executed"]
    bills = client.get("/api/sales").get_json()["sales"]
    assert len(bills) == 1
    assert b.get("replayed") is True


def test_analytics_languages_use_db(client):
    _rice(client, 10)
    _parse(client, "I sold 1 kg of rice for 50 rupees", "lang-s")
    for q in ("आज की बिक्री कितनी है?", "ಇಂದು ಒಟ್ಟು ಮಾರಾಟ ಎಷ್ಟು?", "आजची विक्री किती?"):
        data = _parse(client, q, "lang-q")
        assert data["intent"] == "check_analytics"
        assert data["executed"] is True
        assert data["result"]["total_amount"] == 50


def test_db_error_is_not_success(client, monkeypatch):
    _rice(client, 10)

    def boom(*_a, **_k):
        from errors import ApiError

        raise ApiError("Could not record sale", 500, "db_error")

    monkeypatch.setattr("intents.executor._exec_sale", boom)
    data = _parse(client, "I sold 1 kg of rice for 50 rupees", "err-s")
    assert data["ok"] is False
    assert data["executed"] is False
    assert client.get("/api/sales").get_json()["sales"] == []
