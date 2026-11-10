from __future__ import annotations

from speak import from_payload, sales_reply


def test_sales_templates_four_languages():
    assert "150" in sales_reply("hi", 150, 3, empty=False)
    assert "3" in sales_reply("hi", 150, 3, empty=False)
    assert "150" in sales_reply("kn", 150, 3, empty=False)
    assert "150" in sales_reply("mr", 150, 3, empty=False)
    assert "₹150" in sales_reply("en", 150, 3, empty=False)
    assert "3" in sales_reply("en", 150, 3, empty=False)


def test_speak_uses_only_payload_figures():
    text, lang = from_payload(
        "How much did I sell today?",
        {
            "intent": "check_analytics",
            "result": {"topic": "sales", "total_amount": 150, "transactions": 3},
        },
    )
    assert lang == "en"
    assert "150" in text
    assert "3" in text
    assert "999" not in text


def test_empty_sales_phrases(client):
    for q in (
        "How much did I sell today?",
        "आज की बिक्री कितनी हुई?",
        "ಇವತ್ತಿನ ಮಾರಾಟ ಎಷ್ಟು?",
        "आज किती विक्री झाली?",
    ):
        data = client.post("/api/intents/parse", json={"transcript": q}).get_json()
        assert data["intent"] == "check_analytics", q
        assert data["executed"] is True, q
        assert "total_amount" in data["result"], (q, data["result"])
        assert data["result"]["total_amount"] == 0, q
        assert data["result"]["transactions"] == 0
        assert data["reply_text"]
        assert "0" in data["reply_text"]
        assert "{" not in data["reply_text"]


def test_missing_quantity_reply(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Customer bought almond for 500 rupees"},
    ).get_json()
    assert data["missing"]
    assert data["reply_text"]
    assert data["executed"] is False


def test_gemini_timeout_falls_back_to_flask_reply(client, monkeypatch):
    from errors import ApiError

    def boom(*_a, **_k):
        raise ApiError("Gemini timed out", 504, "llm_timeout")

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", boom)
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "How much did I sell today?"},
    ).get_json()
    assert data["intent"] == "check_analytics"
    assert data["result"]["total_amount"] == 0
    assert "0" in data["reply_text"]


def test_tts_body_only_documented_fields(client, monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr("gnani.tts.Config.GNANI_API_KEY", "test-key-not-real")
    mock = MagicMock()
    mock.status_code = 200
    mock.content = b"RIFF....WAVEfmt "
    mock.headers = {"Content-Type": "audio/wav"}
    with patch("gnani.tts.requests.post", return_value=mock) as post:
        res = client.post("/api/tts", json={"text": "Hello shopkeeper.", "language": "en"})
    assert res.status_code == 200
    body = post.call_args.kwargs.get("json") or post.call_args[1].get("json")
    assert set(body) == {"text", "voice", "model", "language", "audio_config"}
    assert "speed" not in body
    assert "pitch" not in body
    assert body["audio_config"] == {"container": "wav"}


def test_health_exposes_playback_rate(client):
    data = client.get("/api/health").get_json()
    rate = data["gnani"]["tts_playback_rate"]
    assert 1.0 <= rate <= 1.25


def test_tts_missing_key(client, monkeypatch):
    monkeypatch.setattr("gnani.tts.Config.GNANI_API_KEY", "")
    res = client.post("/api/tts", json={"text": "hello", "language": "en"})
    assert res.status_code == 503
    assert res.get_json()["ok"] is False


def test_tts_failure_does_not_drop_parse_text(client, monkeypatch):
    def fail(*_a, **_k):
        raise RuntimeError("tts down")

    monkeypatch.setattr("gnani.tts.synthesize", fail)
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "How much did I sell today?"},
    ).get_json()
    assert data["reply_text"]
    tts = client.post("/api/tts", json={"text": data["reply_text"], "language": "en"})
    assert tts.status_code >= 400
    assert data["reply_text"]
