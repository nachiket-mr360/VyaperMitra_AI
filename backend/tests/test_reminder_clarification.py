from __future__ import annotations


def test_hindi_reminder_ampm_then_confirm(client):
    sid = "rem-hi"
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "कल आठ बजे का रिमाइंडर कर दो।", "session_id": sid, "language_mode": "hi"},
    ).get_json()
    assert first["intent"] == "create_reminder"
    assert first["needs_confirmation"] is False
    assert "time" in (first.get("missing") or [])
    assert first["executed"] is False
    q = first.get("reply_text") or first.get("message") or ""
    assert "सुबह" in q or "समय" in q or "8" in q or "आठ" in q

    second = client.post(
        "/api/intents/parse",
        json={"transcript": "सुबह आठ बजे।", "session_id": sid, "language_mode": "hi"},
    ).get_json()
    assert second["intent"] == "create_reminder"
    assert second["needs_confirmation"] is True
    assert second["executed"] is False
    assert second.get("due_time") == "08:00"
    assert "time" not in (second.get("missing") or [])

    yes = client.post(
        "/api/intents/parse",
        json={"transcript": "हाँ।", "session_id": sid, "language_mode": "hi"},
    ).get_json()
    assert yes["executed"] is True
    assert yes["intent"] in {"confirmation", "create_reminder"}
    text = yes.get("reply_text") or yes.get("message") or ""
    assert "रिमाइंडर" in text or "सेट" in text


def test_english_reminder_evening(client):
    sid = "rem-en"
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "Remind me tomorrow at 8", "session_id": sid, "language_mode": "en"},
    ).get_json()
    assert "time" in (first.get("missing") or [])
    second = client.post(
        "/api/intents/parse",
        json={"transcript": "evening", "session_id": sid, "language_mode": "en"},
    ).get_json()
    assert second["needs_confirmation"] is True
    assert second.get("due_time") == "20:00"
    assert second["executed"] is False


def test_kannada_reminder_morning(client):
    sid = "rem-kn"
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "ನಾಳೆ 8 ಗಂಟೆಗೆ ನೆನಪಿಸು", "session_id": sid, "language_mode": "kn"},
    ).get_json()
    assert first["intent"] == "create_reminder"
    assert "time" in (first.get("missing") or []) or first.get("pending_hour") == 8 or first["needs_confirmation"] is False
    second = client.post(
        "/api/intents/parse",
        json={"transcript": "ಬೆಳಿಗ್ಗೆ", "session_id": sid, "language_mode": "kn"},
    ).get_json()
    assert second["executed"] is False
    if second.get("needs_confirmation"):
        assert second.get("due_time") == "08:00"
