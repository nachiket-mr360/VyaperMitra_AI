from __future__ import annotations


def _seed(client):
    client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 20},
    )
    client.post(
        "/api/products",
        json={"name": "Sugar", "unit": "kg", "low_stock_threshold": 10, "opening_stock": 2},
    )


LOW_STOCK_UTTERANCES = [
    "Which products have low stock?",
    "What items are running low?",
    "किन सामानों का स्टॉक कम है?",
    "किन दो सामानों का स्टॉक कम है?",
    "कौन से प्रोडक्ट कम हैं?",
    "ಯಾವ ವಸ್ತುಗಳ ಸ್ಟಾಕ್ ಕಡಿಮೆ ಇದೆ?",
    "ಯಾವ ವಸ್ತುಗಳು ಕಡಿಮೆ ಇವೆ?",
    "कोणत्या वस्तूंचा स्टॉक कमी आहे?",
    "कोणत्या वस्तू कमी आहेत?",
    "low stock",
]

NAMED_STOCK = [
    "How much rice is left?",
    "चावल का कितना स्टॉक बचा है?",
    "ಅಕ್ಕಿ ಎಷ್ಟು ಸ್ಟಾಕ್ ಇದೆ?",
    "तांदूळ स्टॉक किती आहे?",
]


def test_multilingual_low_stock_list_queries(client):
    _seed(client)
    for q in LOW_STOCK_UTTERANCES:
        data = client.post("/api/intents/parse", json={"transcript": q, "session_id": "r1a"}).get_json()
        assert data["intent"] == "check_analytics", (q, data.get("intent"), data.get("error_code"), data.get("message"))
        assert (data.get("result") or {}).get("topic") == "low_stock", q
        assert data.get("error_code") != "unknown_product", q
        assert data.get("needs_confirmation") is False, q
        assert not data.get("pending_id"), q
        assert data.get("executed") is True, q


def test_named_product_stock_still_resolves(client):
    created = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "opening_stock": 12},
    ).get_json()
    pid = (created.get("product") or {}).get("id")
    if pid:
        client.post(f"/api/products/{pid}/aliases", json={"alias": "तांदळाचा", "language": "mr"})
    for q in NAMED_STOCK:
        data = client.post("/api/intents/parse", json={"transcript": q}).get_json()
        assert data["intent"] == "check_stock", (q, data.get("intent"), data.get("message"))
        assert data.get("error_code") != "unknown_product", q
        assert data.get("needs_confirmation") is False, q
        assert data.get("executed") is True, q


def test_clarification_followup_does_not_repeat_unknown_product(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 40})
    sid = "r1-clarify"
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "I sold 2 kg for 50 rupees", "session_id": sid},
    ).get_json()
    assert first.get("conversation_state") == "clarification" or first.get("missing")
    assert first.get("needs_confirmation") is not True or not first.get("pending_id") or "product" in (first.get("missing") or [])
    second = client.post(
        "/api/intents/parse",
        json={"transcript": "किन दो सामानों का स्टॉक कम है?", "session_id": sid},
    ).get_json()
    assert second.get("error_code") != "unknown_product"
    assert second["intent"] == "check_analytics"
    assert (second.get("result") or {}).get("topic") == "low_stock"
    assert second.get("needs_confirmation") is False

    sid2 = "r1-fill"
    miss = client.post(
        "/api/intents/parse",
        json={"transcript": "I sold 2 kg for 50 rupees", "session_id": sid2},
    ).get_json()
    assert "product" in (miss.get("missing") or []) or miss.get("conversation_state") == "clarification"
    filled = client.post(
        "/api/intents/parse",
        json={"transcript": "rice", "session_id": sid2},
    ).get_json()
    assert filled.get("error_code") != "unknown_product"
    assert filled.get("intent") in {"record_sale", "clarification"}
    if filled.get("intent") == "record_sale":
        assert filled.get("executed") is True
        assert filled.get("needs_confirmation") is False
