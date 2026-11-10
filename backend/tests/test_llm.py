from __future__ import annotations

from llm.validate import validate_llm_payload


def test_validate_sale_fields():
    v = validate_llm_payload(
        {
            "intent": "record_sale",
            "product": "rice",
            "quantity": 1,
            "unit": "kg",
            "amount": 50,
            "missing_fields": [],
            "clarification_required": False,
            "confidence": 0.9,
        }
    )
    assert v["intent"] == "record_sale"
    assert v["product"] == "rice"
    assert v["quantity"] == 1
    assert v["unit"] == "kg"
    assert v["amount"] == 50


def test_validate_rejects_invented_low_confidence():
    v = validate_llm_payload(
        {
            "intent": "record_sale",
            "product": "rice",
            "quantity": 1,
            "unit": "kg",
            "amount": 50,
            "confidence": 0.1,
        }
    )
    assert v["intent"] == "unknown"
    assert v["clarification_required"] is True


def test_validate_sale_missing_amount():
    v = validate_llm_payload(
        {
            "intent": "record_sale",
            "product": "sugar",
            "quantity": 500,
            "unit": "g",
            "amount": None,
            "confidence": 0.8,
        }
    )
    assert "amount" in v["missing"]
    assert v["clarification_required"] is True


def test_gemini_sale_does_not_execute(client, monkeypatch):
    def fake_interpret(transcript, *, today):
        return {
            "intent": "record_sale",
            "product": "rice",
            "quantity": 1,
            "unit": "kg",
            "amount": 50,
            "missing_fields": [],
            "clarification_required": False,
            "confidence": 0.95,
            "_meta": {"latency_s": 0.01, "usage": None, "model": "test"},
        }

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", fake_interpret)
    res = client.post(
        "/api/intents/parse",
        json={"transcript": "Customer ने 1 kg rice लिया, 50 रुपए का।"},
    )
    data = res.get_json()
    assert data["executed"] is False
    assert data["parser"] in {"gemini", "rule_based"}
    assert data["intent"] == "record_sale"
    assert data["quantity"] == 1
    assert data["unit"] == "kg"
    assert data["sale_amount"] == 50
    assert data["executed"] is False
    assert data["needs_confirmation"] is True


def test_validate_recurrence_once_maps_to_none():
    for raw in ("once", "one-time", "onetime", "one_time", None, ""):
        v = validate_llm_payload(
            {
                "intent": "create_reminder",
                "title": "Purchasing goods",
                "due_date": "2026-11-09",
                "due_time": "21:00",
                "recurrence": raw,
                "confidence": 0.95,
            }
        )
        assert v["recurrence"] == "none", raw
    daily = validate_llm_payload(
        {
            "intent": "create_reminder",
            "title": "Milk",
            "due_date": "2026-11-09",
            "due_time": "09:00",
            "recurrence": "daily",
            "confidence": 0.95,
        }
    )
    assert daily["recurrence"] == "daily"


def test_gemini_one_shot_reminder_maps_once_and_needs_confirm(client, monkeypatch):
    def fake_interpret(transcript, *, today):
        return {
            "intent": "create_reminder",
            "title": "Purchasing goods",
            "due_date": "2026-11-09",
            "due_time": "21:00",
            "recurrence": "once",
            "missing_fields": [],
            "clarification_required": False,
            "confidence": 0.95,
            "language": "en",
            "_meta": {"latency_s": 0.01, "usage": None, "model": "test"},
        }

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", fake_interpret)
    utterance = "Schedule a meeting at nine p m tomorrow for purchasing goods."
    res = client.post("/api/intents/parse", json={"transcript": utterance})
    data = res.get_json()
    assert data["parser"] == "gemini"
    assert data["intent"] == "create_reminder"
    assert data["title"] == "Purchasing goods"
    assert data["due_date"] == "2026-11-09"
    assert data["due_time"] == "21:00"
    assert data["recurrence"] == "none"
    assert data["needs_confirmation"] is True
    assert data["executed"] is False
    assert data["pending_id"]
    assert client.get("/api/reminders").get_json()["reminders"] == []
    conf = client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]})
    body = conf.get_json()
    assert conf.status_code == 200
    assert body.get("error") is None
    assert body["executed"] is True
    reminder = body["result"]["reminder"]
    assert reminder["recurrence"] == "none"
    assert reminder["title"] == "Purchasing goods"
    assert reminder["due_date"] == "2026-11-09"
    assert reminder["due_time"] == "21:00"


def test_gemini_unknown_falls_back_to_rules(client, monkeypatch):
    def fake_interpret(transcript, *, today):
        return {
            "intent": "unknown",
            "product": None,
            "quantity": None,
            "unit": None,
            "amount": None,
            "missing_fields": [],
            "clarification_required": True,
            "confidence": 0.3,
        }

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", fake_interpret)
    res = client.post(
        "/api/intents/parse",
        json={"transcript": "I purchased 10 kg rice for my shop"},
    )
    data = res.get_json()
    assert data["parser"] == "rule_based"
    assert data["intent"] == "purchase_stock"
    assert data["executed"] is False
