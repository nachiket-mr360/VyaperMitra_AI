from __future__ import annotations

from intents.visualization import from_analytics_result, validate_visualization


def _seed(client):
    rice = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 20},
    ).get_json()["product"]
    dal = client.post(
        "/api/products",
        json={"name": "Dal", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 20},
    ).get_json()["product"]
    client.post(
        "/api/sales",
        json={
            "idempotency_key": "f-dal",
            "items": [{"product_id": dal["id"], "quantity": 2, "line_total": 100}],
        },
    )
    client.post(
        "/api/sales",
        json={
            "idempotency_key": "f-rice",
            "items": [{"product_id": rice["id"], "quantity": 3, "line_total": 90}],
        },
    )
    return rice, dal


def test_today_yesterday_week_month_trend(client):
    _seed(client)
    today = client.post("/api/intents/parse", json={"transcript": "How much did I sell today?"}).get_json()
    assert today["result"]["topic"] == "sales_summary"
    assert today["result"]["total_amount"] == 190
    y = client.post("/api/intents/parse", json={"transcript": "How much did I sell yesterday?"}).get_json()
    assert y["result"]["period"] == "yesterday"
    w = client.post("/api/intents/parse", json={"transcript": "What were my sales this week?"}).get_json()
    assert w["visualization"]
    assert w["visualization"]["type"] in {"line", "area"}
    m = client.post("/api/intents/parse", json={"transcript": "Show monthly sales."}).get_json()
    assert m["intent"] == "check_analytics"
    t = client.post("/api/intents/parse", json={"transcript": "Show my sales trend for the last 30 days."}).get_json()
    assert t["result"]["topic"] == "sales_trend"
    assert t["visualization"]["points"]


def test_compare_and_products(client):
    _seed(client)
    c = client.post(
        "/api/intents/parse",
        json={"transcript": "Compare this week with last week."},
    ).get_json()
    assert c["result"]["topic"] == "period_compare"
    assert c["visualization"]["type"] == "comparison"
    assert "percent_change" in c["result"]
    b = client.post("/api/intents/parse", json={"transcript": "Which product sells the most?"}).get_json()
    assert b["result"]["topic"] == "best_selling_product"
    p = client.post("/api/intents/parse", json={"transcript": "How much rice did I sell?"}).get_json()
    assert p["result"]["topic"] == "product_sales"


def test_inventory_unknown_empty_profit(client):
    low = client.post("/api/intents/parse", json={"transcript": "Which products are running low?"}).get_json()
    assert low["result"]["topic"] == "low_stock"
    unk = client.post("/api/intents/parse", json={"transcript": "Show products with unknown stock."}).get_json()
    assert unk["result"]["topic"] == "unknown_stock"
    empty = client.post("/api/intents/parse", json={"transcript": "How much did I sell yesterday?"}).get_json()
    assert empty["result"]["total_amount"] == 0
    profit = client.post("/api/intents/parse", json={"transcript": "What is my profit today?"}).get_json()
    assert profit["result"]["topic"] == "unsupported"
    assert profit.get("visualization") in (None, {})


def test_followup_and_chart_and_ambiguous(client):
    _seed(client)
    sid = "f1"
    client.post("/api/intents/parse", json={"transcript": "Show my sales this week.", "session_id": sid})
    y = client.post("/api/intents/parse", json={"transcript": "What about yesterday?", "session_id": sid}).get_json()
    assert y["result"]["topic"] in {"sales_summary", "sales_trend"}
    assert y["result"].get("period") == "yesterday" or "yesterday" in str(y["result"].get("period"))
    cmp_ = client.post(
        "/api/intents/parse",
        json={"transcript": "Compare it with last week.", "session_id": sid},
    ).get_json()
    assert cmp_["result"]["topic"] == "period_compare"
    chart = client.post("/api/intents/parse", json={"transcript": "Show it as a chart.", "session_id": sid}).get_json()
    assert chart.get("visualization") or chart["intent"] == "check_analytics"
    amb = client.post("/api/intents/parse", json={"transcript": "What about it?", "session_id": "none"}).get_json()
    assert amb["intent"] in {"clarification", "general_conversation"}


def test_viz_validate_reject():
    assert validate_visualization({"type": "line"}) is None
    assert validate_visualization({"type": "script", "title": "x", "metric": "recorded_sales_amount", "points": [{"label": "a", "value": 1}]}) is None
    ok = validate_visualization(
        {
            "type": "bar",
            "title": "Sales",
            "metric": "recorded_sales_amount",
            "points": [{"label": "Mon", "value": 10}],
        }
    )
    assert ok and ok["points"][0]["value"] == 10
    assert from_analytics_result({"topic": "unsupported"}) is None


def test_advice_and_memory_and_purchase(client):
    _seed(client)
    adv = client.post("/api/intents/parse", json={"transcript": "How can I improve my sales?"}).get_json()
    assert adv["intent"] == "business_advice"
    assert adv["result"]["profit_available"] is False
    mem = client.post(
        "/api/intents/parse",
        json={"transcript": "Remember that I prefer English.", "session_id": "m"},
    ).get_json()
    assert mem["intent"] == "memory_save"
    p = client.post("/api/intents/parse", json={"transcript": "I purchased 1 kg rice for my shop"}).get_json()
    assert p["intent"] == "purchase_stock"
    assert p["needs_confirmation"] is True


def test_how_is_business_and_hindi(client):
    _seed(client)
    o = client.post("/api/intents/parse", json={"transcript": "How is my business doing?"}).get_json()
    assert o["result"]["topic"] == "overview"
    assert o["visualization"]
    hi = client.post("/api/intents/parse", json={"transcript": "आज की बिक्री"}).get_json()
    assert hi["intent"] == "check_analytics"
