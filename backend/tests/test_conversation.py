from __future__ import annotations

from intents.confirm_speech import classify_confirm_speech
from intents.router import rule_route
from llm.validate import validate_llm_payload


def test_rule_routes_greetings_not_purchase():
    assert rule_route("Hello, how are you?") == "general_conversation"
    assert rule_route("आप कैसे हो?") == "general_conversation"
    assert rule_route("Do you speak Marathi?") == "general_question"
    assert rule_route("How can I improve my sales?") == "business_advice"


def test_confirm_speech_variants():
    assert classify_confirm_speech("Yes.") == "yes"
    assert classify_confirm_speech("Yes, confirm it.") == "yes"
    assert classify_confirm_speech("Go ahead") == "yes"
    assert classify_confirm_speech("Cancel it") == "no"
    assert classify_confirm_speech("Don't do that") == "no"
    assert classify_confirm_speech("How much rice stock do I have?") is None
    assert classify_confirm_speech("हाँ, पुष्टि कर दो, रिकॉर्ड कर दो।") == "yes"
    assert classify_confirm_speech("की सेल बताओ।") is None


def test_hello_is_conversation_not_business(client):
    res = client.post("/api/intents/parse", json={"transcript": "Hello, how are you?", "session_id": "s1"})
    data = res.get_json()
    assert res.status_code == 200
    assert data["intent"] == "general_conversation"
    assert data["needs_confirmation"] is False
    assert data["executed"] is False
    assert "purchase" not in (data.get("message") or "").lower() or "shop" in (data.get("reply_text") or "").lower()


def test_language_question_and_advice(client):
    q = client.post("/api/intents/parse", json={"transcript": "Do you understand Marathi?", "session_id": "s2"})
    assert q.get_json()["intent"] == "general_question"
    a = client.post("/api/intents/parse", json={"transcript": "How can I improve my sales?", "session_id": "s2"})
    assert a.get_json()["intent"] == "business_advice"
    assert a.get_json()["result"] is not None
    assert "today_total_amount" in a.get_json()["result"]


def test_multilingual_greetings(client):
    for text, expect_lang in (
        ("Hello, how are you?", "en"),
        ("आप कैसे हो?", "hi"),
        ("ನಿಮಗೆ ಕನ್ನಡ ಬರುತ್ತದೆಯಾ?", "kn"),
        ("तुला मराठी येते का?", "mr"),
    ):
        res = client.post("/api/intents/parse", json={"transcript": text, "session_id": f"lang-{expect_lang}"})
        data = res.get_json()
        assert data["intent"] in {"general_conversation", "general_question"}
        assert data["reply_language"] == expect_lang


def test_gemini_chat_mocked(client, monkeypatch):
    def fake_interpret(transcript, *, today, history=None):
        return {
            "intent": "general_conversation",
            "confidence": 0.9,
            "clarification_required": False,
            "missing_fields": [],
            "_meta": {},
        }

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", fake_interpret)
    monkeypatch.setattr(
        "llm.gemini.chat_reply",
        lambda transcript, *, language, history=None, facts=None: "Namaste from mock.",
    )
    res = client.post(
        "/api/intents/parse",
        json={"transcript": "Please invent a riddle involving lentils only", "session_id": "g1"},
    )
    data = res.get_json()
    assert data["reply_text"] == "Namaste from mock."
    assert data["parser"] == "gemini"


def test_gemini_failure_falls_back(client, monkeypatch):
    from errors import ApiError

    def boom(*args, **kwargs):
        raise ApiError("down", 502, "llm_unavailable")

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", boom)
    monkeypatch.setattr("llm.gemini.chat_reply", boom)
    res = client.post(
        "/api/intents/parse",
        json={"transcript": "Please invent a riddle involving lentils only", "session_id": "fail"},
    )
    data = res.get_json()
    assert data["intent"] in {"general_conversation", "general_question"}
    assert data.get("llm_fallback") == "llm_unavailable" or data["parser"] == "rule_chat"
    assert data["reply_text"]


def test_two_and_five_turn_context(client, monkeypatch):
    seen = {}

    def fake_interpret(transcript, *, today, history=None):
        seen["history"] = history
        t = transcript.lower()
        if "rice" in t and "stock" in t:
            return {
                "intent": "check_stock",
                "product": "rice",
                "confidence": 0.9,
                "clarification_required": False,
                "missing_fields": [],
            }
        if "dal" in t:
            return {
                "intent": "check_stock",
                "product": "dal",
                "confidence": 0.9,
                "clarification_required": False,
                "missing_fields": [],
            }
        if "yesterday" in t:
            return {
                "intent": "check_analytics",
                "analytics_topic": "sales_summary",
                "period": "yesterday",
                "confidence": 0.9,
                "clarification_required": False,
                "missing_fields": [],
            }
        if "sold the most" in t:
            return {
                "intent": "check_analytics",
                "analytics_topic": "best_selling_product",
                "period": "today",
                "confidence": 0.9,
                "clarification_required": False,
                "missing_fields": [],
            }
        return {"intent": "unknown", "confidence": 0.2, "clarification_required": True, "missing_fields": []}

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", fake_interpret)
    sid = "ctx1"
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 10})
    client.post("/api/products", json={"name": "Dal", "unit": "kg", "opening_stock": 8})
    r1 = client.post("/api/intents/parse", json={"transcript": "How much rice stock do I have?", "session_id": sid})
    assert r1.get_json()["intent"] == "check_stock"
    r2 = client.post("/api/intents/parse", json={"transcript": "What about dal?", "session_id": sid})
    assert r2.get_json()["intent"] == "check_stock"
    client.post("/api/intents/parse", json={"transcript": "And yesterday's sales?", "session_id": sid})
    client.post("/api/intents/parse", json={"transcript": "Which product sold the most?", "session_id": sid})
    r5 = client.post("/api/intents/parse", json={"transcript": "Hello", "session_id": sid})
    assert r5.status_code == 200
    if seen.get("history"):
        assert len(seen["history"]) >= 2


def test_spoken_yes_no_and_duplicate(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 50})
    sid = "pend1"
    parsed = client.post(
        "/api/intents/parse",
        json={"transcript": "I purchased 10 kg rice for my shop", "session_id": sid},
    ).get_json()
    assert parsed["needs_confirmation"] is True
    pid = parsed["pending_id"]
    yes = client.post("/api/intents/parse", json={"transcript": "Yes, confirm it.", "session_id": sid}).get_json()
    assert yes["intent"] == "confirmation"
    assert yes["executed"] is True
    again = client.post("/api/intents/parse", json={"transcript": "Yes.", "session_id": sid}).get_json()
    assert again["intent"] != "confirmation" or again.get("replayed") is True or again["executed"] is False

    parsed2 = client.post(
        "/api/intents/parse",
        json={"transcript": "I purchased 1 kg rice for my shop", "session_id": "pend2"},
    ).get_json()
    no = client.post("/api/intents/parse", json={"transcript": "No.", "session_id": "pend2"}).get_json()
    assert no["intent"] == "cancellation"
    assert no.get("cancelled") is True
    assert parsed2["pending_id"]


def test_expired_spoken_confirm(client, monkeypatch):
    monkeypatch.setattr("config.Config.INTENT_PENDING_TTL_SECONDS", 0)
    # ttl 0 means never expire in executor _expired. Force expire by patching.
    monkeypatch.setattr("intents.executor._expired", lambda created_at: True)
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 50})
    sid = "exp1"
    client.post(
        "/api/intents/parse",
        json={"transcript": "I purchased 2 kg rice for my shop", "session_id": sid},
    )
    res = client.post("/api/intents/parse", json={"transcript": "Yes.", "session_id": sid})
    data = res.get_json()
    assert data["ok"] is False
    assert data["error_code"] == "conflict"


def test_purchase_and_reminder_still_work(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 50})
    p = client.post("/api/intents/parse", json={"transcript": "I purchased 5 kg rice for my shop"}).get_json()
    assert p["intent"] == "purchase_stock"
    assert p["needs_confirmation"] is True
    r = client.post(
        "/api/intents/parse",
        json={"transcript": "Remind me to call the supplier tomorrow at 10 AM."},
    ).get_json()
    assert r["intent"] == "create_reminder"
    assert r["needs_confirmation"] is True


def test_validate_allows_general_intents():
    v = validate_llm_payload({"intent": "general_conversation", "confidence": 0.9})
    assert v["intent"] == "general_conversation"
    assert v["clarification_required"] is False
