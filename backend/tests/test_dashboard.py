from __future__ import annotations

from timeutil import business_date_str


def test_dashboard_empty(client):
    res = client.get("/api/analytics/dashboard")
    data = res.get_json()
    assert res.status_code == 200
    assert data["today"]["total_amount"] == 0
    assert data["today"]["transactions"] == 0
    assert data["yesterday"]["total_amount"] == 0
    assert data["period"]["total_amount"] == 0
    assert len(data["trend"]) >= 1
    assert all(row["total_amount"] == 0 for row in data["trend"])
    assert data["best_sellers"] == []
    assert data["inventory"] == []
    assert data["low_stock"] == []
    assert data["timezone"] == "Asia/Kolkata"
    assert "cash" in data["cash_note"].lower()
    assert "profit" in data["profit_note"].lower()


def test_dashboard_uses_sales_records(client):
    rice = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "opening_stock": 20, "low_stock_threshold": 50},
    ).get_json()["product"]
    today = business_date_str()
    client.post(
        "/api/sales",
        json={
            "transaction_date": today,
            "items": [{"product_id": rice["id"], "quantity": 2, "line_total": 80}],
            "payment_status": "unknown",
        },
    )
    client.post(
        "/api/sales",
        json={
            "transaction_date": "2020-01-15",
            "items": [{"product_id": rice["id"], "quantity": 1, "line_total": 10}],
        },
    )
    dash = client.get(f"/api/analytics/dashboard?from={today}&to={today}").get_json()
    assert dash["today"]["total_amount"] == 80
    assert dash["today"]["transactions"] == 1
    assert dash["period"]["total_amount"] == 80
    assert dash["best_sellers"][0]["name"] == "Rice"
    assert dash["best_sellers"][0]["amount"] == 80
    assert any(p["name"] == "Rice" for p in dash["inventory"])
    assert any(p["name"] == "Rice" for p in dash["low_stock"])
    yest = client.get("/api/analytics/sales/yesterday").get_json()
    assert yest["transactions"] >= 0
    old = client.get("/api/analytics/dashboard?from=2020-01-15&to=2020-01-15").get_json()
    assert old["period"]["total_amount"] == 10


def test_dashboard_invalid_range(client):
    res = client.get("/api/analytics/dashboard?from=2026-02-02&to=2026-02-01")
    assert res.status_code == 400
