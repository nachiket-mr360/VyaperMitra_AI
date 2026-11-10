from __future__ import annotations


def _seed_190(client):
    rice = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 20},
    ).get_json()["product"]
    dal = client.post(
        "/api/products",
        json={"name": "Dal", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 20},
    ).get_json()["product"]
    sugar = client.post(
        "/api/products",
        json={"name": "Sugar", "unit": "kg", "low_stock_threshold": 10, "opening_stock": 2},
    ).get_json()["product"]
    client.post(
        "/api/sales",
        json={
            "idempotency_key": "t-dal",
            "items": [{"product_id": dal["id"], "quantity": 2, "line_total": 100}],
        },
    )
    client.post(
        "/api/sales",
        json={
            "idempotency_key": "t-rice-1",
            "items": [{"product_id": rice["id"], "quantity": 1, "line_total": 45}],
        },
    )
    client.post(
        "/api/sales",
        json={
            "idempotency_key": "t-rice-2",
            "items": [{"product_id": rice["id"], "quantity": 1, "line_total": 45}],
        },
    )
    return rice, dal, sugar


def test_todays_sales_rule_parser(client):
    res = client.post("/api/intents/parse", json={"transcript": "Check today's sales."})
    data = res.get_json()
    assert data["intent"] == "check_analytics"
    assert data["executed"] is True
    assert data["needs_confirmation"] is False
    assert data["result"]["period"] == "today"
    assert data["result"]["topic"] == "sales_summary"
    assert "total_amount" in data["result"]
    assert data["result"]["total_amount"] == 0


def test_low_stock_and_hindi_sales(client):
    low = client.post("/api/intents/parse", json={"transcript": "low stock"}).get_json()
    assert low["intent"] == "check_analytics"
    assert low["result"]["topic"] == "low_stock"
    hi = client.post("/api/intents/parse", json={"transcript": "आज की बिक्री"}).get_json()
    assert hi["intent"] == "check_analytics"
    assert hi["result"]["topic"] == "sales_summary"
    kn = client.post("/api/intents/parse", json={"transcript": "ಇಂದಿನ ಮಾರಾಟ"}).get_json()
    assert kn["intent"] == "check_analytics"
    mr = client.post("/api/intents/parse", json={"transcript": "आजची विक्री"}).get_json()
    assert mr["intent"] == "check_analytics"


def test_gemini_analytics_uses_flask_figures(client, monkeypatch):
    def fake_interpret(transcript, *, today):
        return {
            "intent": "check_analytics",
            "analytics_topic": "sales",
            "period": "today",
            "product": None,
            "quantity": None,
            "amount": 999999,
            "missing_fields": [],
            "clarification_required": False,
            "confidence": 0.99,
        }

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", fake_interpret)
    data = client.post("/api/intents/parse", json={"transcript": "Check today's sales."}).get_json()
    assert data["parser"] in {"gemini", "rule_based"}
    assert data["result"]["total_amount"] == 0
    assert data["result"]["total_amount"] != 999999
    assert data["executed"] is True
    assert data["needs_confirmation"] is False


def test_scope_extraction_variants(client):
    _seed_190(client)
    cases = [
        ("How much did I sell today?", "sales_summary"),
        ("What did I sell today?", "product_breakdown"),
        ("What were today's sales and what products did we sell?", "sales_summary_and_products"),
        ("आज कितनी बिक्री हुई और कौन-कौन से सामान बिके?", "sales_summary_and_products"),
        ("आज मैंने क्या-क्या बेचा?", "product_breakdown"),
        ("ಇವತ್ತು ಎಷ್ಟು ಮಾರಾಟವಾಯಿತು ಮತ್ತು ಯಾವ ವಸ್ತುಗಳು ಮಾರಾಟವಾದವು?", "sales_summary_and_products"),
        ("आज किती विक्री झाली आणि कोणते पदार्थ विकले?", "sales_summary_and_products"),
        ("What is the best selling product?", "best_selling_product"),
        ("How much rice did I sell today?", "product_sales"),
        ("low stock", "low_stock"),
        ("What is my profit today?", "unsupported"),
    ]
    for q, topic in cases:
        data = client.post("/api/intents/parse", json={"transcript": q}).get_json()
        assert data["intent"] == "check_analytics", q
        assert data["result"]["topic"] == topic, (q, data["result"].get("topic"))


def test_combined_demo_figures_four_languages(client):
    _seed_190(client)
    questions = {
        "en": "What were today's sales and which products did I sell?",
        "hi": "आज कितनी बिक्री हुई और कौन-कौन से सामान बिके?",
        "kn": "ಇವತ್ತು ಎಷ್ಟು ಮಾರಾಟವಾಯಿತು ಮತ್ತು ಯಾವ ವಸ್ತುಗಳು ಮಾರಾಟವಾದವು?",
        "mr": "आज किती विक्री झाली आणि कोणते पदार्थ विकले?",
    }
    for lang, q in questions.items():
        data = client.post("/api/intents/parse", json={"transcript": q}).get_json()
        assert data["result"]["topic"] == "sales_summary_and_products"
        assert data["result"]["total_amount"] == 190
        assert data["result"]["transactions"] == 3
        by_name = {p["name"]: p for p in data["result"]["by_product"]}
        assert by_name["Dal"]["quantity"] == 2
        assert by_name["Dal"]["amount"] == 100
        assert by_name["Rice"]["quantity"] == 2
        assert by_name["Rice"]["amount"] == 90
        text = data["reply_text"]
        assert "190" in text
        assert "3" in text
        assert "Dal" in text
        assert "Rice" in text
        assert "100" in text
        assert "90" in text
        assert "{" not in text
        assert data["reply_language"] == lang


def test_summary_only_omits_needless_invention(client):
    _seed_190(client)
    data = client.post("/api/intents/parse", json={"transcript": "How much did I sell today?"}).get_json()
    assert data["result"]["topic"] == "sales_summary"
    assert data["result"]["total_amount"] == 190
    assert "by_product" not in data["result"]
    assert "profit" not in data["reply_text"].lower()


def test_product_only_and_best_and_named(client):
    _seed_190(client)
    sold = client.post("/api/intents/parse", json={"transcript": "What did I sell today?"}).get_json()
    assert sold["result"]["topic"] == "product_breakdown"
    assert any(p["name"] == "Dal" for p in sold["result"]["by_product"])
    best = client.post(
        "/api/intents/parse", json={"transcript": "best selling product"}
    ).get_json()
    assert best["result"]["topic"] == "best_selling_product"
    assert best["result"]["metric"] == "quantity"
    assert best["result"]["best_selling"]["name"] in {"Dal", "Rice"}
    rice = client.post(
        "/api/intents/parse", json={"transcript": "How much rice did I sell today?"}
    ).get_json()
    assert rice["result"]["topic"] == "product_sales"
    assert rice["result"]["by_product"][0]["name"] == "Rice"
    assert rice["result"]["by_product"][0]["amount"] == 90
    low = client.post("/api/intents/parse", json={"transcript": "low stock"}).get_json()
    names = [p["name"] for p in low["result"]["low_stock"]]
    assert "Sugar" in names


def test_empty_db_and_unsupported_and_gemini_wording_timeout(client, monkeypatch):
    empty = client.post("/api/intents/parse", json={"transcript": "What did I sell today?"}).get_json()
    assert empty["result"]["total_amount"] if "total_amount" in empty["result"] else True
    assert empty["result"]["by_product"] == []
    assert empty["reply_text"]
    bad = client.post("/api/intents/parse", json={"transcript": "What is my profit?"}).get_json()
    assert bad["result"]["topic"] == "unsupported"
    assert "190" not in bad["reply_text"]

    from errors import ApiError

    def boom(*_a, **_k):
        raise ApiError("Gemini timed out", 504, "llm_timeout")

    monkeypatch.setattr("llm.gemini.configured", lambda: True)
    monkeypatch.setattr("llm.gemini.interpret", boom)
    monkeypatch.setattr("llm.gemini.word_reply", boom)
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "How much did I sell today?"},
    ).get_json()
    assert data["intent"] == "check_analytics"
    assert data["result"]["total_amount"] == 0
    assert "0" in data["reply_text"]
