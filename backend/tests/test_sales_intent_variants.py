from __future__ import annotations


def _topic(client, q):
    data = client.post("/api/intents/parse", json={"transcript": q}).get_json()
    return data


def test_exact_live_failures(client):
    kn = _topic(client, "ಇವತ್ತು ಒಟ್ಟು ಮಾರಾಟ ಆಗಿದೆ?")
    assert kn["intent"] == "check_analytics"
    assert kn["result"]["topic"] == "sales_summary"
    assert kn["executed"] is True
    assert "?" not in (kn.get("reply_text") or "")
    assert kn["needs_confirmation"] is False

    both = _topic(client, "क्या बिका है और कितना बिका है?")
    assert both["intent"] == "check_analytics"
    assert both["result"]["topic"] == "sales_summary_and_products"
    assert both["executed"] is True

    about = _topic(client, "सेल्स के बारे में बताओ।")
    assert about["intent"] == "check_analytics"
    assert about["result"]["topic"] == "overview"
    assert "क्या बिका" not in (about.get("reply_text") or "")

    total = _topic(client, "टोटल सेल्स के बारे में बताओ।")
    assert total["intent"] == "check_analytics"
    assert total["result"]["topic"] == "sales_summary"
    assert "क्या बिका" not in (total.get("reply_text") or "")


def test_six_sales_intents_en_hi_kn(client):
    rice = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 50},
    ).get_json()["product"]
    client.post(
        "/api/sales",
        json={"idempotency_key": "s1", "items": [{"product_id": rice["id"], "quantity": 3, "line_total": 120}]},
    )
    cases = [
        ("What are my total sales?", "sales_summary"),
        ("अब तक कुल कितनी बिक्री हुई?", "sales_summary"),
        ("ಇವತ್ತು ಒಟ್ಟು ಮಾರಾಟ ಎಷ್ಟು?", "sales_summary"),
        ("Tell me about my sales.", "overview"),
        ("सेल्स के बारे में बताओ।", "overview"),
        ("ನನ್ನ ಮಾರಾಟದ ಬಗ್ಗೆ ಹೇಳಿ.", "overview"),
        ("Which products were sold?", "product_breakdown"),
        ("क्या-क्या बिका है?", "product_breakdown"),
        ("ಯಾವ ಉತ್ಪನ್ನಗಳು ಮಾರಾಟವಾಗಿವೆ?", "product_breakdown"),
        ("How much rice did I sell?", "product_sales"),
        ("कितना चावल बिका?", "product_sales"),
        ("ಎಷ್ಟು ಅಕ್ಕಿ ಮಾರಾಟವಾಗಿದೆ?", "product_sales"),
        ("Which product sells the most?", "best_selling_product"),
        ("सबसे ज्यादा कौन सा प्रोडक्ट बिका?", "best_selling_product"),
        ("ಯಾವ ಉತ್ಪನ್ನ ಹೆಚ್ಚು ಮಾರಾಟವಾಗಿದೆ?", "best_selling_product"),
        ("Show my sales trend.", "sales_trend"),
        ("इस महीने की बिक्री कैसी रही?", "sales_trend"),
        ("ಈ ತಿಂಗಳ ಮಾರಾಟ ಹೇಗಿದೆ?", "sales_trend"),
    ]
    for q, topic in cases:
        data = _topic(client, q)
        assert data["intent"] == "check_analytics", q
        assert data["result"]["topic"] == topic, (q, data["result"].get("topic"))
        assert data["needs_confirmation"] is False, q
        assert data["executed"] is True, q


def test_analytics_not_mutation(client):
    n = len(client.get("/api/products").get_json()["products"])
    _topic(client, "सेल्स के बारे में बताओ।")
    _topic(client, "ಇವತ್ತು ಒಟ್ಟು ಮಾರಾಟ ಆಗಿದೆ?")
    assert len(client.get("/api/products").get_json()["products"]) == n
