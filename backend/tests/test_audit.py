"""Phase 2 correctness audit: idempotency, money, concurrency, validation, integrity."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch

from config import Config
from db import apply_migrations, get_connection
from money import line_paise, rupees_to_paise, units_to_micro


def _rice(client, stock=10):
    res = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "opening_stock": stock, "low_stock_threshold": 2},
    )
    assert res.status_code == 201, res.get_json()
    return res.get_json()["product"]


def test_idempotency_same_payload_replays(client):
    product = _rice(client, 20)
    payload = {
        "idempotency_key": "k1",
        "items": [{"product_id": product["id"], "quantity": 2, "line_total": 80}],
    }
    a = client.post("/api/sales", json=payload)
    b = client.post("/api/sales", json=payload)
    assert a.status_code == 201
    assert b.status_code == 200
    assert b.get_json()["replayed"] is True
    assert a.get_json()["sale"]["id"] == b.get_json()["sale"]["id"]
    sales = client.get("/api/sales").get_json()["sales"]
    assert len(sales) == 1
    assert client.get("/api/stock").get_json()["stock"][0]["current_stock"] == 18


def test_idempotency_different_payload_rejected(client):
    product = _rice(client, 20)
    client.post(
        "/api/sales",
        json={
            "idempotency_key": "k2",
            "items": [{"product_id": product["id"], "quantity": 1, "line_total": 40}],
        },
    )
    res = client.post(
        "/api/sales",
        json={
            "idempotency_key": "k2",
            "items": [{"product_id": product["id"], "quantity": 3, "line_total": 120}],
        },
    )
    assert res.status_code == 409
    assert res.get_json()["error"]["code"] == "idempotency_conflict"
    assert client.get("/api/stock").get_json()["stock"][0]["current_stock"] == 19
    assert len(client.get("/api/sales").get_json()["sales"]) == 1


def test_failed_sale_does_not_consume_idempotency_key(client):
    product = _rice(client, 10)
    payload = {
        "idempotency_key": "k-fail",
        "items": [{"product_id": product["id"], "quantity": 1, "unit_price": 10}],
    }
    with patch("services.sales.apply_stock_change", side_effect=RuntimeError("boom")):
        res = client.post("/api/sales", json=payload)
        assert res.status_code == 500
    retry = client.post("/api/sales", json=payload)
    assert retry.status_code == 201
    assert retry.get_json()["replayed"] is False
    assert client.get("/api/stock").get_json()["stock"][0]["current_stock"] == 9


def test_money_rounding_half_up():
    assert rupees_to_paise("10.005") == 1001
    assert rupees_to_paise("10.004") == 1000
    assert rupees_to_paise(0.1) + rupees_to_paise(0.2) == rupees_to_paise(0.3)
    qty = units_to_micro(3)
    assert line_paise(qty, 333) == 999  # 3 * ₹3.33


def test_sale_total_uses_paise(client):
    product = _rice(client, 10)
    res = client.post(
        "/api/sales",
        json={
            "items": [
                {"product_id": product["id"], "quantity": 1, "unit_price": 0.1},
                {"product_id": product["id"], "quantity": 1, "unit_price": 0.2},
            ]
        },
    )
    assert res.status_code == 201
    assert res.get_json()["sale"]["total_amount"] == 0.3
    summary = client.get("/api/analytics/sales/summary").get_json()
    assert summary["total_amount"] == 0.3


def test_concurrent_sales_do_not_oversell(tmp_path, monkeypatch):
    db_path = tmp_path / "concurrent.db"
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setattr("config.Config.DATABASE_PATH", str(db_path))
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    with application.test_client() as c:
        product = _rice(c, 1)
        pid = product["id"]

    results: list[int] = []
    barrier = threading.Barrier(2)

    def sell():
        barrier.wait()
        with application.test_client() as tc:
            res = tc.post(
                "/api/sales",
                json={"items": [{"product_id": pid, "quantity": 1, "unit_price": 10}]},
            )
            results.append(res.status_code)

    t1 = threading.Thread(target=sell)
    t2 = threading.Thread(target=sell)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert sorted(results) in ([201, 409], [409, 201])
    with application.test_client() as c:
        stock = c.get("/api/stock").get_json()["stock"][0]["current_stock"]
        assert stock == 0
        assert len(c.get("/api/sales").get_json()["sales"]) == 1
        assert stock >= 0


def test_invalid_unit_and_product_id(client):
    bad_unit = client.post("/api/products", json={"name": "Oil", "unit": "barrel"})
    assert bad_unit.status_code == 400
    missing = client.get("/api/products/99999")
    assert missing.status_code == 404
    sale = client.post(
        "/api/sales",
        json={"items": [{"product_id": 99999, "quantity": 1, "unit_price": 1}]},
    )
    assert sale.status_code == 404
    qty = client.post("/api/products", json={"name": "Oil", "unit": "l", "opening_stock": 0})
    assert qty.status_code == 400


def test_protected_stock_fields_on_patch(client):
    product = _rice(client, 5)
    res = client.patch(
        f"/api/products/{product['id']}",
        json={"current_stock": 999, "name": "Rice Premium"},
    )
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "protected_field"
    still = client.get(f"/api/products/{product['id']}").get_json()["product"]
    assert still["current_stock"] == 5


def test_reject_spoofed_movement_type(client):
    product = _rice(client, 5)
    res = client.post(
        "/api/stock/purchase",
        json={"product_id": product["id"], "quantity": 1, "movement_type": "sale"},
    )
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "invalid_value"


def test_foreign_keys_and_ledger_matches_stock(client):
    product = _rice(client, 8)
    pid = product["id"]
    client.post("/api/sales", json={"items": [{"product_id": pid, "quantity": 3, "line_total": 90}]})
    path = Config.DATABASE_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    prod = conn.execute("SELECT current_stock FROM products WHERE id = ?", (pid,)).fetchone()
    ledger = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) AS q FROM stock_movements WHERE product_id = ?",
        (pid,),
    ).fetchone()
    assert int(prod["current_stock"]) == int(ledger["q"])
    try:
        conn.execute(
            "INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, line_total) VALUES (1, 999, 1, 1, 1)"
        )
        conn.commit()
        assert False, "FK should reject"
    except sqlite3.IntegrityError:
        conn.rollback()
    conn.close()


def test_migration_on_existing_foundation(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr("config.Config.DATABASE_PATH", str(db_path))
    conn = sqlite3.connect(db_path)
    conn.executescript((Path(__file__).resolve().parents[1] / "migrations" / "001_foundation.sql").read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (1, '001_foundation.sql', 'x')"
    )
    conn.commit()
    conn.close()
    conn = get_connection(immediate=False)
    apply_migrations(conn)
    versions = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    assert 2 in versions and 3 in versions
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "products" in tables and "sales" in tables
    conn.close()
