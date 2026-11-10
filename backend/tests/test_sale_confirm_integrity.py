from __future__ import annotations


def test_hindi_confirm_commits_sale_and_today_total(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: True)

    def boom_chat(*a, **k):
        raise AssertionError("chat_reply must not run while confirming a sale")

    monkeypatch.setattr("llm.gemini.chat_reply", boom_chat)
    monkeypatch.setattr(
        "llm.gemini.interpret",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("interpret must not run on confirm")),
    )

    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 50})
    sid = "sale-integrity"
    proposed = client.post(
        "/api/intents/parse",
        json={
            "transcript": "A customer took 2 kg rice at 100 rupees",
            "session_id": sid,
        },
    ).get_json()
    assert proposed["intent"] == "record_sale"
    assert proposed["needs_confirmation"] is False
    assert proposed["executed"] is True
    sale = (proposed.get("result") or {}).get("sale") or {}
    assert sale.get("id")
    assert abs(float(sale.get("total_amount") or 0) - 100) < 0.01
    assert "सुमन" not in (proposed.get("reply_text") or "")

    today = client.get("/api/analytics/sales/today").get_json()
    assert today["total_amount"] == 100 or abs(float(today["total_amount"]) - 100) < 0.01
    assert today["transactions"] >= 1

    again = client.post(
        "/api/intents/parse",
        json={"transcript": "A customer took 2 kg rice at 100 rupees", "session_id": sid},
    ).get_json()
    assert again.get("replayed") is True
    today2 = client.get("/api/analytics/sales/today").get_json()
    assert today2["transactions"] == today["transactions"]


def test_non_confirm_while_pending_does_not_fake_success(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.chat_reply", lambda *a, **k: "I recorded the sale to Suman.")
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 50})
    sid = "sale-wait"
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "A customer took 2 kg rice at 100 rupees", "session_id": sid},
    ).get_json()
    assert first["executed"] is True
    wait = client.post(
        "/api/intents/parse",
        json={"transcript": "चावल राइस।", "session_id": sid},
    ).get_json()
    text = wait.get("reply_text") or wait.get("message") or ""
    assert "Suman" not in text
    assert "I recorded the sale to Suman" not in text
    today = client.get("/api/analytics/sales/today").get_json()
    assert float(today["total_amount"] or 0) == 100
