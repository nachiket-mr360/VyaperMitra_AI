from __future__ import annotations

from intents.confirm_speech import classify_confirm_speech
from intents.unclear import is_unclear_transcript, recovery_message


def test_unclear_fillers():
    assert is_unclear_transcript("")
    assert is_unclear_transcript("hmm")
    assert is_unclear_transcript("uh")
    assert not is_unclear_transcript("5 kg")
    assert not is_unclear_transcript("I purchased rice")


def test_recovery_languages():
    assert "repeat" in recovery_message("en").lower()
    assert recovery_message("hi")
    assert recovery_message("kn")
    assert recovery_message("mr")


def test_parse_unclear_does_not_mutate(client):
    rice = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 40},
    ).get_json()["product"]
    stock = rice["current_stock"]
    data = client.post("/api/intents/parse", json={"transcript": "hmm", "session_id": "n1"}).get_json()
    assert data["executed"] is False
    assert data["needs_confirmation"] is False
    assert data["intent"] == "unclear"
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == stock


def test_empty_stt_style_parse(client):
    data = client.post("/api/intents/parse", json={"transcript": "..."}).get_json()
    assert data.get("executed") is False
    assert data["intent"] == "unclear"


def test_ambiguous_speech_not_confirm(client):
    client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 40},
    )
    sid = "n2"
    pending = client.post(
        "/api/intents/parse",
        json={"transcript": "I purchased 2 kg rice", "session_id": sid},
    ).get_json()
    assert pending["needs_confirmation"] is True
    stock = client.get("/api/products").get_json()["products"][0]["current_stock"]
    amb = client.post("/api/intents/parse", json={"transcript": "hmm", "session_id": sid}).get_json()
    assert amb["executed"] is False
    assert classify_confirm_speech("hmm") is None
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == stock
    maybe = client.post("/api/intents/parse", json={"transcript": "maybe later", "session_id": sid}).get_json()
    assert maybe.get("intent") != "confirmation" or maybe["executed"] is False
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == stock
