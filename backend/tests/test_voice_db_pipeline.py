from __future__ import annotations


def _rice(client, stock: float = 20):
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


def _parse(client, text: str, session_id: str):
    return client.post(
        "/api/intents/parse",
        json={"transcript": text, "session_id": session_id},
    ).get_json()


def test_hindi_rice_sale_commits(client):
    _rice(client, 10)
    data = _parse(client, "एक कस्टमर ने 50 रुपये का 1 किलो Rice लिया।", "hi-rice")
    assert data["intent"] == "record_sale"
    assert data["executed"] is True
    assert data["needs_confirmation"] is False
    sale = data["result"]["sale"]
    assert sale["id"]
    assert sale["total_amount"] == 50
    assert "दर्ज कर दी गई है" in (data.get("reply_text") or data["message"])
    bills = client.get("/api/sales").get_json()["sales"]
    assert len(bills) == 1
    today = client.get("/api/analytics/sales/today").get_json()
    assert today["total_amount"] == 50
    dash = client.get("/api/analytics/dashboard").get_json()
    assert dash["today"]["total_amount"] == 50


def test_multilingual_rice_sales(client):
    _rice(client, 40)
    phrases = (
        ("en-s", "A customer took 1 kg Rice for 50 rupees."),
        ("kn-s", "ಒಬ್ಬ ಗ್ರಾಹಕ 1 ಕಿಲೋ ಅಕ್ಕಿ 50 ರೂಪಾಯಿಗೆ ತೆಗೆದುಕೊಂಡ."),
        ("mr-s", "एका ग्राहकाने 1 किलो तांदूळ घेतले, 50 रुपये."),
    )
    for sid, text in phrases:
        data = _parse(client, text, sid)
        assert data["intent"] == "record_sale", text
        assert data["executed"] is True, data
    bills = client.get("/api/sales").get_json()["sales"]
    assert len(bills) == 3


def test_correct_then_cancel_last_bill(client):
    _rice(client, 10)
    sid = "g1-follow"
    sale = _parse(client, "एक कस्टमर ने 50 रुपये का 1 किलो Rice लिया।", sid)
    assert sale["executed"]
    sale_id = sale["result"]["sale"]["id"]

    corr = _parse(client, "उसकी कीमत 60 रुपये कर दो।", sid)
    assert corr["intent"] == "correct_sale"
    assert corr["needs_confirmation"] is True
    done = client.post(
        "/api/intents/confirm",
        json={"pending_id": corr["pending_id"], "session_id": sid},
    ).get_json()
    assert done["executed"] is True
    bills = client.get("/api/sales").get_json()["sales"]
    assert len(bills) == 1
    assert bills[0]["id"] == sale_id
    assert client.get("/api/analytics/sales/today").get_json()["total_amount"] == 60

    cancel = _parse(client, "नहीं, इसे हटा दो।", sid)
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


def test_health_names_shop_database(client):
    data = client.get("/api/health").get_json()
    assert data["database"]["connected"] is True
    assert data["database"]["demo"] is False
    assert data["database"]["name"].endswith(".db")
    assert "vyaparmitra_demo.db" not in (data["database"].get("path") or "")
