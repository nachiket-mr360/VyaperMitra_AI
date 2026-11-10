from __future__ import annotations

from intents.router import fallback_chat, is_greeting, rule_route


def test_unrelated_questions_are_not_the_default_greeting():
    greeting = fallback_chat("general_conversation", "Hello", "hi")
    for q in (
        "Explain the difference between AI, ML and Deep Learning",
        "What is cloud computing?",
        "Tell me about crop loans",
        "What products do you recommend for a kirana?",
    ):
        assert is_greeting(q) is False
        assert rule_route(q) in {None, "general_question", "business_advice"}
        text = fallback_chat(rule_route(q) or "unknown", q, "hi")
        assert text != greeting
        assert "व्यापारी मित्र हूँ। सामान्य सवाल" not in text


def test_greeting_is_still_fast(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no interpret")))
    monkeypatch.setattr("llm.gemini.chat_reply", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no chat")))
    data = client.post("/api/intents/parse", json={"transcript": "Good morning", "session_id": "cq-hi"}).get_json()
    assert data["intent"] == "general_conversation"
    assert "shop" in (data.get("reply_text") or data.get("message") or "").lower() or "दुकान" in (
        data.get("reply_text") or ""
    )


def test_general_knowledge_uses_chat_not_greeting(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: True)

    def chat(transcript, **kwargs):
        assert "Deep Learning" in transcript or "cloud" in transcript.lower()
        return "AI is the field; ML is a subset; deep learning uses neural nets."

    monkeypatch.setattr("llm.gemini.chat_reply", chat)
    monkeypatch.setattr("llm.gemini.interpret", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no interpret")))
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Explain the difference between AI, ML and Deep Learning", "session_id": "cq-gk"},
    ).get_json()
    text = data.get("reply_text") or data.get("message") or ""
    assert "neural" in text.lower() or "subset" in text.lower()
    assert "I am VyaparMitra. You can chat generally" not in text
    assert data["intent"] in {"general_question", "general_conversation"}


def test_unknown_without_gemini_asks_clarification(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: False)
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Tell me about crop loans in Karnataka", "session_id": "cq-unk"},
    ).get_json()
    text = data.get("reply_text") or data.get("message") or ""
    assert "नमस्ते। मैं व्यापारी मित्र हूँ" not in text
    assert "Hello. I am VyaparMitra. You can chat generally" not in text
    assert "दुकान के रिकॉर्ड से नहीं जुड़ा" not in text
    assert data["intent"] in {"clarification", "general_question"}


def test_language_switch_auto(client):
    a = client.post(
        "/api/intents/parse",
        json={"transcript": "Hello", "session_id": "cq-sw", "language_mode": "auto"},
    ).get_json()
    assert a["reply_language"] == "en"
    b = client.post(
        "/api/intents/parse",
        json={"transcript": "नमस्ते, स्टॉक कितना है?", "session_id": "cq-sw", "language_mode": "auto"},
    ).get_json()
    assert b["reply_language"] == "hi"


def test_followup_how_much_uses_last_product(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_qty": 40})
    client.post(
        "/api/sales",
        json={"lines": [{"product_id": 1, "qty": 5, "unit": "kg", "line_total": 100}], "notes": None},
    )
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "Which product sells the most?", "session_id": "cq-fu"},
    ).get_json()
    assert first["intent"] == "check_analytics"
    second = client.post(
        "/api/intents/parse",
        json={"transcript": "How much did I sell?", "session_id": "cq-fu"},
    ).get_json()
    assert second["intent"] == "check_analytics"
    assert second.get("executed") is not False or second.get("result")


def test_kannada_question_not_greeting(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: False)
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "ಕೃಷಿ ಸಾಲದ ಬಗ್ಗೆ ಹೇಳಿ", "session_id": "cq-kn", "language_mode": "kn"},
    ).get_json()
    text = data.get("reply_text") or data.get("message") or ""
    assert "ನಾನು ವ್ಯಾಪಾರಿ ಮಿತ್ರ. ಸಾಮಾನ್ಯ ಪ್ರಶ್ನೆ" not in text
