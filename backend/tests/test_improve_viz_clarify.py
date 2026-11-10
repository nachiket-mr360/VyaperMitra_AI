from __future__ import annotations

from intents.visualization import from_analytics_result, validate_visualization
from intents.clarify import apply_fill, extract_fill, first_missing, question


def _rice(client):
    client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 80},
    )


def test_product_hbar_viz_has_points(client):
    created = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 80},
    ).get_json()["product"]
    client.post(
        "/api/sales",
        json={"idempotency_key": "iv1", "items": [{"product_id": created["id"], "quantity": 2, "line_total": 80}]},
    )
    data = client.post("/api/intents/parse", json={"transcript": "Which product sells the most?"}).get_json()
    viz = data.get("visualization")
    assert viz
    assert viz["type"] == "hbar"
    assert viz["points"]
    assert all("label" in p and p["value"] is not None for p in viz["points"])
    assert validate_visualization(viz)


def test_invalid_viz_rejected():
    assert validate_visualization({"type": "hbar", "title": "x", "metric": "recorded_sales_amount", "points": []}) is None
    assert from_analytics_result({"topic": "unsupported"}) is None


def test_purchase_asks_quantity_not_confirm(client):
    _rice(client)
    sid = "c1"
    a = client.post("/api/intents/parse", json={"transcript": "I purchased rice", "session_id": sid}).get_json()
    assert a["executed"] is False
    assert a["needs_confirmation"] is False
    assert a["conversation_state"] == "clarification"
    assert "how much" in (a["reply_text"] or "").lower() or "quantity" in (a.get("missing") or [])
    stock = client.get("/api/products").get_json()["products"][0]["current_stock"]
    b = client.post("/api/intents/parse", json={"transcript": "50 kg", "session_id": sid}).get_json()
    assert b["intent"] == "purchase_stock"
    assert b["quantity"] == 50
    assert b["needs_confirmation"] is True
    assert b["executed"] is False
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == stock
    conf = client.post("/api/intents/confirm", json={"pending_id": b["pending_id"], "session_id": sid}).get_json()
    assert conf["executed"] is True


def test_reminder_asks_time(client):
    sid = "c2"
    a = client.post(
        "/api/intents/parse",
        json={"transcript": "Remind me about the meeting tomorrow", "session_id": sid},
    ).get_json()
    assert a["executed"] is False
    if a.get("needs_confirmation"):
        return
    assert a["conversation_state"] == "clarification"
    b = client.post("/api/intents/parse", json={"transcript": "at 9 PM", "session_id": sid}).get_json()
    assert b["executed"] is False
    assert b["needs_confirmation"] is True


def test_metric_clarification(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Which product performs best?", "session_id": "c3"},
    ).get_json()
    assert data["conversation_state"] == "clarification"
    assert data["executed"] is False
    follow = client.post(
        "/api/intents/parse",
        json={"transcript": "total sales amount", "session_id": "c3"},
    ).get_json()
    assert follow["intent"] == "check_analytics"
    assert follow["needs_confirmation"] is False


def test_hindi_purchase_clarify(client):
    _rice(client)
    sid = "c4"
    a = client.post("/api/intents/parse", json={"transcript": "मैंने चावल खरीदा", "session_id": sid}).get_json()
    assert a["executed"] is False
    assert a["needs_confirmation"] is False
    b = client.post("/api/intents/parse", json={"transcript": "10 किलो", "session_id": sid}).get_json()
    assert b["quantity"] == 10
    assert b["needs_confirmation"] is True


def test_extract_fill_units():
    f = extract_fill("50 kg")
    assert f["quantity"] == 50
    assert f["unit"] == "kg"
    slot = {"intent": "purchase_stock", "product_query": "rice", "missing": ["quantity", "unit"]}
    m = apply_fill(slot, f)
    assert m["missing"] == []
    assert first_missing(["unit", "quantity"]) == "quantity"
    q = question(["quantity"], lang="en", product="rice", intent="purchase_stock")
    assert "rice" in q.lower()


def test_rules_parse_skips_slow_path(client):
    data = client.post("/api/intents/parse", json={"transcript": "How much did I sell today?"}).get_json()
    assert data["intent"] == "check_analytics"
    assert data.get("timings_ms", {}).get("total") is not None
