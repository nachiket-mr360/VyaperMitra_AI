"""Inventory and sales tests. Isolated SQLite file via conftest client fixture."""

from __future__ import annotations

from unittest.mock import patch

from timeutil import business_date_str


def _create_rice(client, stock=10, threshold=2):
    res = client.post(
        "/api/products",
        json={
            "name": "Rice",
            "unit": "kg",
            "low_stock_threshold": threshold,
            "opening_stock": stock,
        },
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()["product"]


def test_create_and_get_product(client):
    product = _create_rice(client)
    assert product["name"] == "Rice"
    assert product["current_stock"] == 10
    detail = client.get(f"/api/products/{product['id']}")
    assert detail.status_code == 200
    assert detail.get_json()["product"]["unit"] == "kg"


def test_duplicate_product_rejected(client):
    _create_rice(client)
    res = client.post("/api/products", json={"name": " rice ", "unit": "kg"})
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "duplicate"


def test_alias_create_and_duplicate(client):
    product = _create_rice(client)
    res = client.post(
        f"/api/products/{product['id']}/aliases",
        json={"alias": "chawal", "language": "hi"},
    )
    assert res.status_code == 201
    dup = client.post(
        f"/api/products/{product['id']}/aliases",
        json={"alias": "Chawal"},
    )
    assert dup.status_code == 409


def test_stock_purchase_and_history(client):
    product = _create_rice(client, stock=5)
    res = client.post(
        "/api/stock/purchase",
        json={"product_id": product["id"], "quantity": 3, "unit_cost": 40},
    )
    assert res.status_code == 201
    assert res.get_json()["movement"]["current_stock"] == 8
    hist = client.get(f"/api/stock/movements?product_id={product['id']}")
    types = [m["movement_type"] for m in hist.get_json()["movements"]]
    assert "purchase" in types
    assert "opening" in types


def test_stock_adjustment_and_negative_rejected(client):
    product = _create_rice(client, stock=4)
    down = client.post(
        "/api/stock/adjustment",
        json={"product_id": product["id"], "quantity": -1, "notes": "spoilage"},
    )
    assert down.status_code == 201
    assert down.get_json()["movement"]["current_stock"] == 3
    too_far = client.post(
        "/api/stock/adjustment",
        json={"product_id": product["id"], "quantity": -10},
    )
    assert too_far.status_code == 409
    stock = client.get("/api/stock").get_json()["stock"][0]["current_stock"]
    assert stock == 3


def test_negative_quantity_on_purchase(client):
    product = _create_rice(client)
    res = client.post(
        "/api/stock/purchase",
        json={"product_id": product["id"], "quantity": -1},
    )
    assert res.status_code == 400


def test_sale_records_and_reduces_stock(client):
    product = _create_rice(client, stock=10)
    res = client.post(
        "/api/sales",
        json={
            "idempotency_key": "sale-rice-1",
            "items": [{"product_id": product["id"], "quantity": 5, "line_total": 200}],
        },
    )
    assert res.status_code == 201, res.get_json()
    sale = res.get_json()["sale"]
    assert sale["total_amount"] == 200
    assert sale["items"][0]["quantity"] == 5
    assert sale["items"][0]["unit_price"] == 40
    stock = client.get("/api/stock").get_json()["stock"][0]["current_stock"]
    assert stock == 5
    moves = client.get("/api/stock/movements").get_json()["movements"]
    assert any(m["movement_type"] == "sale" and m["quantity"] == -5 for m in moves)


def test_insufficient_stock(client):
    product = _create_rice(client, stock=2)
    res = client.post(
        "/api/sales",
        json={"items": [{"product_id": product["id"], "quantity": 5, "unit_price": 10}]},
    )
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "insufficient_stock"
    stock = client.get("/api/stock").get_json()["stock"][0]["current_stock"]
    assert stock == 2


def test_invalid_price(client):
    product = _create_rice(client)
    res = client.post(
        "/api/sales",
        json={"items": [{"product_id": product["id"], "quantity": 1, "unit_price": -5}]},
    )
    assert res.status_code == 400


def test_duplicate_sale_idempotency(client):
    product = _create_rice(client, stock=20)
    payload = {
        "idempotency_key": "same-key",
        "items": [{"product_id": product["id"], "quantity": 2, "line_total": 80}],
    }
    first = client.post("/api/sales", json=payload)
    second = client.post("/api/sales", json=payload)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.get_json()["replayed"] is True
    assert first.get_json()["sale"]["id"] == second.get_json()["sale"]["id"]
    stock = client.get("/api/stock").get_json()["stock"][0]["current_stock"]
    assert stock == 18


def test_sale_rollback_on_failure(client):
    product = _create_rice(client, stock=10)
    with patch("services.sales.apply_stock_change", side_effect=RuntimeError("boom")):
        res = client.post(
            "/api/sales",
            json={"items": [{"product_id": product["id"], "quantity": 1, "unit_price": 10}]},
        )
        assert res.status_code == 500
    stock = client.get("/api/stock").get_json()["stock"][0]["current_stock"]
    assert stock == 10
    listed = client.get("/api/sales").get_json()["sales"]
    assert listed == []


def test_sales_totals_and_low_stock(client):
    product = _create_rice(client, stock=5, threshold=4)
    client.post(
        "/api/sales",
        json={"items": [{"product_id": product["id"], "quantity": 2, "line_total": 100}]},
    )
    today = client.get("/api/analytics/sales/today").get_json()
    assert today["total_amount"] == 100
    assert today["transactions"] == 1
    summary = client.get("/api/analytics/sales/summary").get_json()
    assert summary["total_amount"] == 100
    low = client.get("/api/stock/low").get_json()["stock"]
    assert len(low) == 1
    assert low[0]["current_stock"] == 3


def test_date_boundaries_kolkata(client):
    product = _create_rice(client, stock=20)
    today = business_date_str()
    client.post(
        "/api/sales",
        json={
            "transaction_date": "2020-01-15",
            "items": [{"product_id": product["id"], "quantity": 1, "line_total": 10}],
        },
    )
    client.post(
        "/api/sales",
        json={
            "transaction_date": today,
            "items": [{"product_id": product["id"], "quantity": 1, "line_total": 25}],
        },
    )
    old = client.get("/api/analytics/sales?date=2020-01-15").get_json()
    now = client.get("/api/analytics/sales/today").get_json()
    assert old["total_amount"] == 10
    assert old["transactions"] == 1
    assert now["date"] == today
    assert now["total_amount"] == 25


def test_multi_item_sale(client):
    rice = _create_rice(client, stock=10)
    dal = client.post("/api/products", json={"name": "Dal", "unit": "kg", "opening_stock": 8})
    dal_id = dal.get_json()["product"]["id"]
    res = client.post(
        "/api/sales",
        json={
            "items": [
                {"product_id": rice["id"], "quantity": 1, "unit_price": 40},
                {"product_id": dal_id, "quantity": 2, "line_total": 120},
            ]
        },
    )
    assert res.status_code == 201
    assert res.get_json()["sale"]["total_amount"] == 160
