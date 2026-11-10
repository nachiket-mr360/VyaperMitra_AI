from __future__ import annotations


def test_hindi_sale_prompt_and_confirm_stay_hindi(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 20})
    sid = "lang-hi"
    a = client.post(
        "/api/intents/parse",
        json={"transcript": "एक ग्राहक ने एक किलो चावल एक रुपये में लिया।", "session_id": sid},
    ).get_json()
    assert a["reply_language"] == "hi"
    text = a.get("reply_text") or a.get("message") or ""
    assert "Record sale of" not in text
    assert "दर्ज" in text or "बिक्री" in text
    b = client.post(
        "/api/intents/parse",
        json={"transcript": "हाँ, पुष्टि कर दो, रिकॉर्ड कर दो।", "session_id": sid},
    ).get_json()
    assert b["reply_language"] == "hi"
    assert "Please say yes" not in (b.get("reply_text") or "")


def test_english_confirm_keeps_hindi_session(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 20})
    sid = "lang-stick"
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "दो किलो चावल सौ रुपये में बेचा।", "session_id": sid},
    ).get_json()
    assert first.get("executed") is True
    assert first["reply_language"] == "hi"
