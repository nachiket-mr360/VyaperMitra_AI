from __future__ import annotations

from intents.language import detect_input_language, resolve_reply_language, tamil_limitation_message
from intents.router import rule_route


def test_greeting_fast_path_skips_gemini(client, monkeypatch):
    called = {"interpret": 0, "chat": 0}

    def boom_interpret(*args, **kwargs):
        called["interpret"] += 1
        raise AssertionError("interpret should not run for greetings")

    def boom_chat(*args, **kwargs):
        called["chat"] += 1
        raise AssertionError("chat_reply should not run for greetings")

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", boom_interpret)
    monkeypatch.setattr("llm.gemini.chat_reply", boom_chat)
    res = client.post("/api/intents/parse", json={"transcript": "Hello", "session_id": "fast-1"})
    data = res.get_json()
    assert res.status_code == 200
    assert data["intent"] == "general_conversation"
    assert data["parser"] == "rule_chat"
    assert called["interpret"] == 0
    assert called["chat"] == 0
    assert data.get("timings_ms", {}).get("gemini") in (None, 0)


def test_thanks_is_fast_path(client):
    assert rule_route("thank you") == "general_conversation"
    data = client.post("/api/intents/parse", json={"transcript": "धन्यवाद", "session_id": "fast-2"}).get_json()
    assert data["intent"] == "general_conversation"
    assert data["reply_language"] == "hi"


def test_language_mode_overrides_detection(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Hello", "session_id": "lang-ov", "language_mode": "kn"},
    ).get_json()
    assert data["reply_language"] == "kn"
    assert data.get("detected_input_language") == "en"


def test_auto_detects_each_turn(client):
    a = client.post(
        "/api/intents/parse",
        json={"transcript": "Hello", "session_id": "switch", "language_mode": "auto"},
    ).get_json()
    b = client.post(
        "/api/intents/parse",
        json={"transcript": "आप कैसे हो?", "session_id": "switch", "language_mode": "auto"},
    ).get_json()
    assert a["reply_language"] == "en"
    assert b["reply_language"] == "hi"


def test_tamil_not_classified_as_hindi():
    assert detect_input_language("வணக்கம்") == "ta"
    lang, det, _ = resolve_reply_language("வணக்கம்", mode="auto")
    assert det == "ta"
    assert "Tamil" in tamil_limitation_message("en") or "तमिल" in tamil_limitation_message("hi")


def test_tamil_transcript_explains_limit(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "வணக்கம்", "session_id": "ta-1", "language_mode": "auto"},
    ).get_json()
    assert data["intent"] == "unsupported_language"
    assert data["detected_input_language"] == "ta"
    assert "Tamil" in data["message"] or "तमिल" in data["message"] or "ತಮಿಳು" in data["message"]


def test_kannada_greeting_language(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "ನಮಸ್ಕಾರ", "session_id": "kn-1", "language_mode": "auto"},
    ).get_json()
    assert data["reply_language"] == "kn"


def test_sales_inventory_analytics_csv(client):
    empty = client.get("/api/exports/sales.csv")
    assert empty.status_code == 200
    assert empty.data.startswith(b"\xef\xbb\xbf")
    assert b"sale_id" in empty.data
    inv = client.get("/api/exports/inventory.csv")
    assert inv.status_code == 200
    assert b"product_id" in inv.data
    an = client.get("/api/exports/analytics.csv")
    assert an.status_code == 200
    assert b"recorded_sales_inr" in an.data
    assert b"Profit is not included" in an.data


def test_sales_csv_respects_date_filter(client):
    from services.products import create_product
    from services.sales import create_sale

    p = create_product("CSV Rice", "kg", opening_stock=10)
    create_sale(
        [{"product_id": p["id"], "quantity": 1, "unit_price": 50}],
        transaction_date="2026-01-15",
        idempotency_key="csv-1",
        notes=None,
    )
    create_sale(
        [{"product_id": p["id"], "quantity": 1, "unit_price": 80}],
        transaction_date="2026-02-01",
        idempotency_key="csv-2",
        notes=None,
    )
    only = client.get("/api/exports/sales.csv?from=2026-01-01&to=2026-01-31")
    body = only.data.decode("utf-8-sig")
    assert "2026-01-15" in body
    assert "2026-02-01" not in body
    assert "CSV Rice" in body
