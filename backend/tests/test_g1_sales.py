from __future__ import annotations


def _rice(client):
    return client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 50},
    ).get_json()["product"]


def _dal(client):
    return client.post(
        "/api/products",
        json={"name": "Dal", "unit": "kg", "low_stock_threshold": 1, "opening_stock": 40},
    ).get_json()["product"]


def _sell(client, product, qty, total, key):
    return client.post(
        "/api/sales",
        json={"idempotency_key": key, "items": [{"product_id": product["id"], "quantity": qty, "line_total": total}]},
    ).get_json()["sale"]


def _mutate(client, path, body, session="sess-g1"):
    body = {**body, "session_id": session}
    proposed = client.post(path, json=body)
    assert proposed.status_code == 202, proposed.get_json()
    data = proposed.get_json()
    assert data["needs_confirmation"] is True
    assert data["executed"] is False
    confirmed = client.post(
        "/api/intents/confirm",
        json={"pending_id": data["pending_id"], "session_id": session},
    )
    assert confirmed.status_code == 200, confirmed.get_json()
    return confirmed.get_json()


def test_history_filter_and_detail(client):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-a")
    listed = client.get(f"/api/sales?id={sale['id']}").get_json()["sales"]
    assert len(listed) == 1
    detail = client.get(f"/api/sales/{sale['id']}").get_json()["sale"]
    assert detail["items"]
    assert detail["lines"]
    assert detail["financials"]["cash_received"] is None
    assert detail["financials"]["net_recorded"] == 200


def test_correct_then_return(client):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-b")
    key = sale["lines"][0]["line_key"]
    corr = _mutate(client, f"/api/sales/{sale['id']}/corrections", {"line_key": key, "quantity": 3})
    assert corr["result"]["sale"]["financials"]["net_recorded"] == 120
    ret = _mutate(client, f"/api/sales/{sale['id']}/returns", {"line_key": key, "quantity": 1})
    assert ret["result"]["sale"]["financials"]["net_recorded"] == 80
    stock = client.get("/api/stock").get_json()["stock"]
    rice_row = next(s for s in stock if s["name"] == "Rice")
    assert rice_row["current_stock"] == 48


def test_return_then_qty_below_returned_rejected(client):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-c")
    key = sale["lines"][0]["line_key"]
    _mutate(client, f"/api/sales/{sale['id']}/returns", {"line_key": key, "quantity": 2})
    proposed = client.post(
        f"/api/sales/{sale['id']}/corrections",
        json={"line_key": key, "quantity": 1, "session_id": "sess-g1"},
    )
    assert proposed.status_code == 202
    bad = client.post(
        "/api/intents/confirm",
        json={"pending_id": proposed.get_json()["pending_id"], "session_id": "sess-g1"},
    )
    assert bad.status_code == 409


def test_price_correct_partial_return(client):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-d")
    key = sale["lines"][0]["line_key"]
    _mutate(client, f"/api/sales/{sale['id']}/corrections", {"line_key": key, "unit_price": 50})
    ret = _mutate(client, f"/api/sales/{sale['id']}/returns", {"line_key": key, "quantity": 2})["result"]["sale"]
    assert ret["returns"][0]["unit_price"] == 50
    assert ret["financials"]["net_recorded"] == 150


def test_return_then_cancel_restores_remaining(client):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-e")
    key = sale["lines"][0]["line_key"]
    _mutate(client, f"/api/sales/{sale['id']}/returns", {"line_key": key, "quantity": 1})
    _mutate(client, f"/api/sales/{sale['id']}/cancel", {})
    stock = next(s for s in client.get("/api/stock").get_json()["stock"] if s["name"] == "Rice")
    assert stock["current_stock"] == 50
    detail = client.get(f"/api/sales/{sale['id']}").get_json()["sale"]
    assert detail["status"] == "cancelled"
    assert detail["financials"]["net_recorded"] == 0
    still = client.get("/api/sales").get_json()["sales"]
    assert any(s["id"] == sale["id"] for s in still)


def test_idempotent_replay(client):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-f")
    key = sale["lines"][0]["line_key"]
    a = _mutate(client, f"/api/sales/{sale['id']}/returns", {"line_key": key, "quantity": 1})
    b = client.post(
        f"/api/sales/{sale['id']}/returns",
        json={"line_key": key, "quantity": 1, "session_id": "sess-g1"},
    )
    assert b.status_code == 202
    assert client.get(f"/api/sales/{sale['id']}").get_json()["sale"]["financials"]["net_recorded"] == a["result"]["sale"]["financials"]["net_recorded"]
    c1 = _mutate(client, f"/api/sales/{sale['id']}/cancel", {})
    assert c1["result"]["sale"]["status"] == "cancelled"
    again = client.post(f"/api/sales/{sale['id']}/cancel", json={"session_id": "sess-g1"})
    assert again.status_code == 202
    conf = client.post("/api/intents/confirm", json={"pending_id": again.get_json()["pending_id"], "session_id": "sess-g1"})
    assert conf.status_code in {200, 409}


def test_over_return_rejected(client):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-g")
    key = sale["lines"][0]["line_key"]
    _mutate(client, f"/api/sales/{sale['id']}/corrections", {"line_key": key, "quantity": 3})
    proposed = client.post(
        f"/api/sales/{sale['id']}/returns",
        json={"line_key": key, "quantity": 4, "session_id": "sess-g1"},
    )
    bad = client.post(
        "/api/intents/confirm",
        json={"pending_id": proposed.get_json()["pending_id"], "session_id": "sess-g1"},
    )
    assert bad.status_code == 409


def test_product_change_then_cancel(client):
    rice = _rice(client)
    dal = _dal(client)
    sale = _sell(client, rice, 5, 200, "g1-h")
    key = sale["lines"][0]["line_key"]
    _mutate(
        client,
        f"/api/sales/{sale['id']}/corrections",
        {"line_key": key, "product_id": dal["id"], "quantity": 5, "unit_price": 50},
    )
    _mutate(client, f"/api/sales/{sale['id']}/cancel", {})
    stock = {s["name"]: s["current_stock"] for s in client.get("/api/stock").get_json()["stock"]}
    assert stock["Rice"] == 50
    assert stock["Dal"] == 40


def test_voice_last_sale_and_cancel_needs_confirm(client):
    rice = _rice(client)
    sale = _sell(client, rice, 2, 80, "g1-v")
    shown = client.post("/api/intents/parse", json={"transcript": "Find my last sale"}).get_json()
    assert shown["intent"] == "show_sale"
    assert shown["result"]["id"] == sale["id"]
    cancel = client.post(
        "/api/intents/parse",
        json={"transcript": f"Cancel bill number {sale['id']}", "session_id": "voice-g1"},
    ).get_json()
    assert cancel["needs_confirmation"] is True
    still = client.get(f"/api/sales/{sale['id']}").get_json()["sale"]
    assert still["status"] != "cancelled"


def test_http_mutation_requires_confirm(client):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-direct")
    key = sale["lines"][0]["line_key"]
    proposed = client.post(
        f"/api/sales/{sale['id']}/returns",
        json={"line_key": key, "quantity": 1, "session_id": "s-a"},
    )
    assert proposed.status_code == 202
    detail = client.get(f"/api/sales/{sale['id']}").get_json()["sale"]
    assert detail["financials"]["net_recorded"] == 200
    forbidden = client.post(
        "/api/intents/confirm",
        json={"pending_id": proposed.get_json()["pending_id"], "session_id": "other"},
    )
    assert forbidden.status_code == 403


def test_analytics_scopes_use_net(client):
    rice = _rice(client)
    kept = _sell(client, rice, 5, 200, "g1-net-a")
    gone = _sell(client, rice, 4, 160, "g1-net-b")
    key = kept["lines"][0]["line_key"]
    _mutate(client, f"/api/sales/{kept['id']}/corrections", {"line_key": key, "quantity": 3})
    _mutate(client, f"/api/sales/{kept['id']}/returns", {"line_key": key, "quantity": 1})
    _mutate(client, f"/api/sales/{gone['id']}/cancel", {})
    day = kept["transaction_date"]
    daily = client.get(f"/api/analytics/sales?date={day}").get_json()
    today = client.get("/api/analytics/sales/today").get_json()
    dash = client.get(f"/api/analytics/dashboard?from={day}&to={day}").get_json()
    byp = client.get("/api/analytics/sales/by-product").get_json()["products"]
    summary = client.get("/api/analytics/sales/summary").get_json()
    assert daily["total_amount"] == 80
    assert today["total_amount"] == 80
    assert dash["period"]["total_amount"] == 80
    assert dash["today"]["total_amount"] == 80
    assert summary["total_amount"] == 80
    rice_row = next(r for r in daily["by_product"] if r["name"] == "Rice")
    assert rice_row["quantity"] == 2
    assert rice_row["amount"] == 80
    assert next(r for r in byp if r["name"] == "Rice")["amount"] == 80
    assert abs(sum(p["amount"] for p in dash["by_product"]) - dash["period"]["total_amount"]) < 0.001
    trend_day = next(r for r in dash["trend"] if r["date"] == day)
    assert trend_day["total_amount"] == 80
    assert abs(sum(r["total_amount"] for r in dash["trend"]) - dash["period"]["total_amount"]) < 0.001


def test_g1_session_gate(client, monkeypatch):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-sess")
    key = sale["lines"][0]["line_key"]
    missing = client.post(
        f"/api/sales/{sale['id']}/returns",
        json={"line_key": key, "quantity": 1},
    )
    assert missing.status_code == 400
    proposed = client.post(
        f"/api/sales/{sale['id']}/returns",
        json={"line_key": key, "quantity": 1, "session_id": "sess-ok"},
    )
    pid = proposed.get_json()["pending_id"]
    assert client.post("/api/intents/confirm", json={"pending_id": pid}).status_code == 403
    assert client.post("/api/intents/confirm", json={"pending_id": pid, "session_id": "wrong"}).status_code == 403
    monkeypatch.setattr("intents.executor.Config.INTENT_PENDING_TTL_SECONDS", 1)
    import time

    time.sleep(1.1)
    expired = client.post("/api/intents/confirm", json={"pending_id": pid, "session_id": "sess-ok"})
    assert expired.status_code == 409
    still = client.get(f"/api/sales/{sale['id']}").get_json()["sale"]
    assert still["financials"]["net_recorded"] == 200


def test_product_analytics_matches_net(client):
    rice = _rice(client)
    sale = _sell(client, rice, 5, 200, "g1-an")
    key = sale["lines"][0]["line_key"]
    _mutate(client, f"/api/sales/{sale['id']}/corrections", {"line_key": key, "quantity": 3})
    _mutate(client, f"/api/sales/{sale['id']}/returns", {"line_key": key, "quantity": 1})
    day = sale["transaction_date"]
    block = client.get(f"/api/analytics/sales?date={day}").get_json()
    dash = client.get("/api/analytics/dashboard").get_json()
    rice_row = next(r for r in block["by_product"] if r["name"] == "Rice")
    assert rice_row["quantity"] == 2
    assert rice_row["amount"] == 80
    assert block["total_amount"] == 80
    assert abs(sum(p["amount"] for p in dash["by_product"]) - dash["period"]["total_amount"]) < 0.001


def test_concurrent_over_return(client):
    from concurrent.futures import ThreadPoolExecutor, wait

    from errors import ApiError
    from services.sale_lifecycle import return_qty

    rice = _rice(client)
    sale = _sell(client, rice, 3, 120, "g1-race")
    key = sale["lines"][0]["line_key"]
    sale_id = sale["id"]
    outcomes: list[str] = []

    def attempt(tok: str) -> None:
        try:
            return_qty(sale_id, line_key=key, quantity=2, idempotency_key=tok)
            outcomes.append("ok")
        except ApiError as exc:
            outcomes.append(exc.code)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = [pool.submit(attempt, "race-a"), pool.submit(attempt, "race-b")]
        wait(futs)
        for f in futs:
            f.result()
    assert outcomes.count("ok") == 1
    assert "invalid_value" in outcomes or "conflict" in outcomes
    detail = client.get(f"/api/sales/{sale_id}").get_json()["sale"]
    assert detail["lines"][0]["returned_quantity"] == 2
    assert len(detail["returns"]) == 1
    stock = next(s for s in client.get("/api/stock").get_json()["stock"] if s["name"] == "Rice")
    assert stock["current_stock"] == 49


def test_009_migration_on_populated_copy(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path

    from db import MIGRATIONS_DIR, apply_migrations, get_connection

    pre = tmp_path / "pre009.db"
    monkeypatch.setattr("config.Config.DATABASE_PATH", str(pre))
    conn = sqlite3.connect(str(pre))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        ver = int(path.name.split("_", 1)[0])
        if ver >= 9:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        if ver == 3:
            from db import _apply_003_data

            _apply_003_data(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, datetime('now'))",
            (ver, path.name),
        )
    conn.execute(
        """
        INSERT INTO products (name, normalized_name, unit, current_stock, low_stock_threshold, active, stock_known, created_at, updated_at)
        VALUES ('Rice', 'rice', 'kg', 50000000, 1000000, 1, 1, datetime('now'), datetime('now'))
        """
    )
    pid = conn.execute("SELECT id FROM products").fetchone()[0]
    conn.execute(
        """
        INSERT INTO sales (transaction_date, total_amount, payment_status, notes, created_at)
        VALUES ('2026-01-15', 20000, 'unknown', 'old', datetime('now'))
        """
    )
    sid = conn.execute("SELECT id FROM sales").fetchone()[0]
    conn.execute(
        """
        INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, line_total)
        VALUES (?, ?, 5000000, 4000, 20000)
        """,
        (sid, pid),
    )
    conn.commit()
    item_before = dict(conn.execute("SELECT * FROM sale_items").fetchone())
    sale_before = dict(conn.execute("SELECT * FROM sales").fetchone())
    conn.close()

    clone = tmp_path / "clone.db"
    clone.write_bytes(pre.read_bytes())
    monkeypatch.setattr("config.Config.DATABASE_PATH", str(clone))
    live = get_connection(immediate=False)
    apply_migrations(live)
    live.execute("PRAGMA foreign_keys=ON")
    assert live.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert live.execute("PRAGMA foreign_key_check").fetchall() == []
    item_after = dict(live.execute("SELECT * FROM sale_items").fetchone())
    sale_after = {k: live.execute("SELECT * FROM sales").fetchone()[k] for k in sale_before}
    for k, v in item_before.items():
        assert item_after[k] == v
    for k, v in sale_before.items():
        assert sale_after[k] == v
    assert live.execute("SELECT COUNT(*) FROM sale_lines").fetchone()[0] == 1
    apply_migrations(live)
    assert live.execute("SELECT COUNT(*) FROM sale_lines").fetchone()[0] == 1
    bak = Path(str(clone) + ".pre-009.bak")
    assert bak.exists()
    live.close()

