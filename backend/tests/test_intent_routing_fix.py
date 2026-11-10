from __future__ import annotations


def test_hindi_total_sales_not_product(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "तुम मुझे बता सकते हो टोटल सेल्स कितना हुआ आज तक?"},
    ).get_json()
    assert data["intent"] == "check_analytics"
    assert data["result"]["topic"] == "sales_summary"
    assert "product named" not in (data.get("reply_text") or "").lower()
    assert "no product" not in (data.get("message") or "").lower()
    assert data["executed"] is True
    assert data["needs_confirmation"] is False


def test_kannada_total_sales_answers(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "ಇವತ್ತು ನನ್ನ ಒಟ್ಟು ಮಾರಾಟ ಎಷ್ಟು?"},
    ).get_json()
    assert data["intent"] == "check_analytics"
    assert data["result"]["topic"] == "sales_summary"
    text = data.get("reply_text") or ""
    assert "ಎಷ್ಟು" not in text or "ರೂಪಾಯಿ" in text
    assert data["reply_language"] == "kn"


def test_total_sales_four_languages(client):
    cases = [
        ("How much total sales have I made today?", "en"),
        ("आज मेरी कुल बिक्री कितनी हुई?", "hi"),
        ("ಇವತ್ತು ನನ್ನ ಒಟ್ಟು ಮಾರಾಟ ಎಷ್ಟು?", "kn"),
        ("आज माझी एकूण विक्री किती झाली?", "mr"),
    ]
    for q, lang in cases:
        data = client.post("/api/intents/parse", json={"transcript": q}).get_json()
        assert data["intent"] == "check_analytics", q
        assert data["result"]["topic"] == "sales_summary", q
        assert data["reply_language"] == lang, q


def test_sales_so_far(client):
    for q in (
        "What is my total sales so far?",
        "अब तक मेरी कुल बिक्री कितनी है?",
        "ಇಲ್ಲಿಯವರೆಗೆ ಒಟ್ಟು ಎಷ್ಟು ಮಾರಾಟವಾಗಿದೆ?",
        "आतापर्यंत किती विक्री झाली?",
    ):
        data = client.post("/api/intents/parse", json={"transcript": q}).get_json()
        assert data["intent"] == "check_analytics", q
        assert data["result"]["period"] == "all", q


def test_ranking_and_product_sales_and_stock(client):
    rice = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 40},
    ).get_json()["product"]
    client.post(
        "/api/sales",
        json={"idempotency_key": "r1", "items": [{"product_id": rice["id"], "quantity": 2, "line_total": 80}]},
    )
    best = client.post("/api/intents/parse", json={"transcript": "Which product sells the most?"}).get_json()
    assert best["result"]["topic"] == "best_selling_product"
    hi = client.post("/api/intents/parse", json={"transcript": "सबसे ज्यादा कौन सा प्रोडक्ट बिका?"}).get_json()
    assert hi["result"]["topic"] == "best_selling_product"
    kn = client.post("/api/intents/parse", json={"transcript": "ಯಾವ ಉತ್ಪನ್ನ ಹೆಚ್ಚು ಮಾರಾಟವಾಗಿದೆ?"}).get_json()
    assert kn["result"]["topic"] == "best_selling_product"
    mr = client.post("/api/intents/parse", json={"transcript": "कोणता प्रॉडक्ट सर्वात जास्त विकला गेला?"}).get_json()
    assert mr["result"]["topic"] == "best_selling_product"
    sold = client.post("/api/intents/parse", json={"transcript": "How much rice did I sell?"}).get_json()
    assert sold["intent"] == "check_analytics"
    assert sold["result"]["topic"] == "product_sales"
    stock = client.post("/api/intents/parse", json={"transcript": "How much rice is in stock?"}).get_json()
    assert stock["intent"] == "check_stock"
    assert stock["executed"] is True


def test_general_knowledge_and_overview(client):
    q = client.post("/api/intents/parse", json={"transcript": "What is artificial intelligence?"}).get_json()
    assert q["intent"] == "general_question"
    assert q["executed"] is False
    biz = client.post("/api/intents/parse", json={"transcript": "Tell me about my business."}).get_json()
    assert biz["intent"] == "check_analytics"
    assert biz["result"]["topic"] == "overview"


def test_code_switch_sales_not_mutation(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "today टोटल सेल्स कितना हुआ"},
    ).get_json()
    assert data["intent"] == "check_analytics"
    assert data["needs_confirmation"] is False
    assert data["executed"] is True


def test_followup_dal_stock(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 10})
    client.post("/api/products", json={"name": "Dal", "unit": "kg", "opening_stock": 5})
    sid = "f1"
    a = client.post(
        "/api/intents/parse",
        json={"transcript": "How much rice stock do I have?", "session_id": sid},
    ).get_json()
    assert a["intent"] == "check_stock"
    b = client.post("/api/intents/parse", json={"transcript": "What about dal?", "session_id": sid}).get_json()
    assert b["intent"] == "check_stock"
