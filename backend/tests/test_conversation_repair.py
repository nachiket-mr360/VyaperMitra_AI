from __future__ import annotations

from errors import ApiError
from intents.parser import parse_transcript
from intents.router import fallback_chat, rule_route, unknown_question_reply
from services.exports import csv_bytes


SHOP_RECORD_HI = "दुकान के रिकॉर्ड से नहीं जुड़ा"


def test_rule_route_hindi_difference():
    assert rule_route("मुझे AI और ML का डिफरेंस बताओ।") == "general_question"
    assert rule_route("Explain AI, ML and Deep Learning.") == "general_question"


def test_fallback_general_question_is_not_shop_record():
    text = fallback_chat("general_question", "Explain AI", "hi")
    assert SHOP_RECORD_HI not in text
    assert "भाषा मॉडल" in text or "सामान्य ज्ञान" in text


def test_general_question_skips_interpret(client, monkeypatch):
    called = {"interpret": 0, "chat": 0}

    def interpret(*a, **k):
        called["interpret"] += 1
        raise AssertionError("interpret must not run for general questions")

    def chat(*a, **k):
        called["chat"] += 1
        return "AI is a field of computer science."

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", interpret)
    monkeypatch.setattr("llm.gemini.chat_reply", chat)
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Explain AI, ML and Deep Learning.", "session_id": "gk-once"},
    ).get_json()
    assert called["interpret"] == 0
    assert called["chat"] == 1
    assert "computer science" in (data.get("reply_text") or "")


def test_interpret_failure_does_not_call_chat(client, monkeypatch):
    from errors import ApiError

    called = {"chat": 0}

    def boom(*a, **k):
        raise ApiError("down", 503, "llm_unavailable")

    def chat(*a, **k):
        called["chat"] += 1
        return "should not run"

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", boom)
    monkeypatch.setattr("llm.gemini.chat_reply", chat)
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "लिया दस किलो चावल", "session_id": "shop-fail"},
    ).get_json()
    assert called["chat"] == 0
    assert data.get("llm_fallback") == "llm_unavailable"
    assert data.get("reply_text")
    assert "language model" in (data.get("reply_text") or "").lower() or "भाषा मॉडल" in (data.get("reply_text") or "")


def test_english_general_knowledge_mocked_gemini(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr(
        "llm.gemini.chat_reply",
        lambda *a, **k: "AI is the broad field; ML learns from data; deep learning uses neural nets.",
    )
    monkeypatch.setattr(
        "llm.gemini.interpret",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("interpret should not run")),
    )
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Explain AI, ML and Deep Learning.", "session_id": "gk-en"},
    ).get_json()
    assert data["intent"] == "general_question"
    assert "neural" in (data.get("reply_text") or "").lower()
    assert SHOP_RECORD_HI not in (data.get("reply_text") or "")


def test_hindi_educational_mocked_gemini(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr(
        "llm.gemini.chat_reply",
        lambda *a, **k: "एआई व्यापक क्षेत्र है और एमएल उससे सीखने की विधि है।",
    )
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "मुझे AI और ML का डिफरेंस बताओ।", "session_id": "gk-hi"},
    ).get_json()
    assert data["intent"] == "general_question"
    text = data.get("reply_text") or ""
    assert "एमएल" in text or "एआई" in text
    assert SHOP_RECORD_HI not in text


def _raise(code: str, status: int = 502):
    def _inner(*args, **kwargs):
        raise ApiError("Language model failed.", status, code)

    return _inner


def test_gemini_auth_failure_honest(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.chat_reply", _raise("llm_unauthorized", 401))
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Explain cloud computing", "session_id": "gk-auth"},
    ).get_json()
    text = data.get("reply_text") or data.get("message") or ""
    assert data.get("llm_fallback") == "llm_unauthorized"
    assert SHOP_RECORD_HI not in text
    assert "language model" in text.lower() or "भाषा मॉडल" in text


def test_gemini_timeout_honest(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.chat_reply", _raise("llm_timeout", 504))
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "What is photosynthesis?", "session_id": "gk-to"},
    ).get_json()
    assert data.get("llm_fallback") == "llm_timeout"
    assert SHOP_RECORD_HI not in (data.get("reply_text") or "")


def test_gemini_unavailable_honest(client, monkeypatch):
    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.chat_reply", _raise("llm_unavailable", 502))
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Explain gravity", "session_id": "gk-un"},
    ).get_json()
    assert data.get("llm_fallback") == "llm_unavailable"
    assert "could not answer" in (data.get("reply_text") or "").lower() or "भाषा मॉडल" in (data.get("reply_text") or "")


def test_hindi_first_person_purchase(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 10})
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "आज मैंने राइस लिया दस किलो।", "session_id": "pur-1"},
    ).get_json()
    assert data["intent"] == "purchase_stock"
    assert data["quantity"] == 10
    assert data["needs_confirmation"] is True
    bought = client.post(
        "/api/intents/parse",
        json={"transcript": "मैंने दस किलो चावल खरीदा।", "session_id": "pur-2"},
    ).get_json()
    assert bought["intent"] == "purchase_stock"
    assert bought["quantity"] == 10


def test_hindi_customer_sale(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 20})
    data = client.post(
        "/api/intents/parse",
        json={
            "transcript": "एक ग्राहक ने दो किलो चावल लिया और सौ रुपये दिए।",
            "session_id": "sale-hi",
        },
    ).get_json()
    assert data["intent"] == "record_sale"
    assert data["quantity"] == 2
    assert data["sale_amount"] == 100
    assert data["needs_confirmation"] is False
    assert data["executed"] is True


def test_hindi_number_words_parser():
    d = parse_transcript("मैंने पाँच किलो चावल खरीदा")
    assert d.intent == "purchase_stock"
    assert d.quantity == 5


def test_kannada_business_overview(client):
    data = client.post(
        "/api/intents/parse",
        json={
            "transcript": "ಇಂದು ನನ್ನ ಅಂಗಡಿಯಲ್ಲಿ ಎಷ್ಟು ವ್ಯಾಪಾರ ಆಯಿತು?",
            "session_id": "kn-biz",
        },
    ).get_json()
    assert data["intent"] == "check_analytics"
    assert data["needs_confirmation"] is False
    assert data.get("result") is not None


def test_kannada_rice_stock(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 12})
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "ನನ್ನ ಅಂಗಡಿಯಲ್ಲಿ ಎಷ್ಟು ಅಕ್ಕಿ ಉಳಿದಿದೆ?", "session_id": "kn-st"},
    ).get_json()
    assert data["intent"] == "check_stock"
    assert data["executed"] is True
    assert "12" in (data.get("reply_text") or data.get("message") or "")


def test_session_confirm_gate(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 40})
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "I purchased 2 kg of rice", "session_id": "own-a"},
    ).get_json()
    pid = data["pending_id"]
    wrong = client.post("/api/intents/confirm", json={"pending_id": pid, "session_id": "other"})
    assert wrong.status_code == 403
    ok = client.post("/api/intents/confirm", json={"pending_id": pid, "session_id": "own-a"})
    assert ok.status_code == 200
    again = client.post("/api/intents/confirm", json={"pending_id": pid, "session_id": "own-a"})
    assert again.status_code == 200
    assert again.get_json().get("replayed") is True


def test_csv_formula_injection():
    raw = csv_bytes(["name"], [["=HYPERLINK(1)", "+cmd", "@x"]])
    text = raw.decode("utf-8")
    assert "'=HYPERLINK(1)" in text
    assert "'+cmd" in text
    assert "'@x" in text


def test_unknown_clarification_short(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "xyzzy plugh 12345", "session_id": "unk-1"},
    ).get_json()
    text = data.get("reply_text") or ""
    assert SHOP_RECORD_HI not in text
    assert data["intent"] in {"clarification", "general_question", "unknown"}
    assert unknown_question_reply("en") in text or "didn't catch" in text.lower() or "language model" in text.lower()
