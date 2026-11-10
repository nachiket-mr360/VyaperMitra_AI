from __future__ import annotations

from db import get_connection
from intents.resolver import resolve_product


def _parse(client, text: str):
    return client.post("/api/intents/parse", json={"transcript": text})


def test_rice_aliases_one_id(client):
    created = client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 10})
    assert created.status_code == 201
    pid = created.get_json()["product"]["id"]
    names = ["rice", "Chawal", "चावल", "Akki", "ಅಕ್ಕಿ", "Tandul", "तांदूळ"]
    ids = set()
    for n in names:
        hit = resolve_product(n)
        assert hit.unknown is False, n
        assert hit.ambiguous is False, n
        assert hit.product is not None
        assert hit.product["id"] == pid
        ids.add(hit.product["id"])
    assert ids == {pid}


def test_create_unknown_on_confirm_not_before(client):
    data = _parse(client, "I purchased 4 kg of millet").get_json()
    assert data["needs_confirmation"] is True
    assert client.get("/api/products").get_json()["products"] == []
    conf = client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]})
    assert conf.status_code == 200
    products = client.get("/api/products").get_json()["products"]
    assert len(products) == 1
    assert products[0]["current_stock"] == 4
    assert products[0]["stock_known"] is True
    again = client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]})
    assert again.get_json()["replayed"] is True
    assert len(client.get("/api/products").get_json()["products"]) == 1


def test_unknown_stock_sale_does_not_invent_qty(client):
    data = _parse(client, "I sold 1 kg of millet for 40 rupees").get_json()
    assert data["create_product"] is True
    conf = client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]})
    assert conf.status_code == 200
    product = client.get("/api/products").get_json()["products"][0]
    assert product["stock_known"] is False
    assert product["current_stock"] is None
    sales = client.get("/api/sales").get_json()["sales"]
    assert len(sales) == 1
    assert sales[0]["total_amount"] == 40
    conn = get_connection()
    try:
        n = conn.execute("SELECT COUNT(*) AS c FROM stock_movements").fetchone()["c"]
    finally:
        conn.close()
    assert n == 0


def test_ambiguous_products(client):
    client.post("/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 1})
    client.post("/api/products", json={"name": "Rice Bran", "unit": "kg", "opening_stock": 1})
    data = _parse(client, "I purchased 1 kg of rice").get_json()
    assert data.get("error_code") != "unknown_product"
    # exact "rice" matches canonical Rice only
    assert data["needs_confirmation"] is True
    assert data["create_product"] is False


def test_stock_known_backfill_zero_without_movements(client):
    """0-qty and no movements must not stay marked counted (006/007 UPDATE)."""
    from pathlib import Path

    conn = get_connection()
    try:
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO products (
                name, normalized_name, unit, current_stock, low_stock_threshold,
                active, created_at, updated_at, stock_known
            ) VALUES ('Ghost', 'ghost', 'kg', 0, 0, 1, '2020-01-01', '2020-01-01', 1)
            """
        )
        conn.execute("COMMIT")
        sql = (Path(__file__).resolve().parents[1] / "migrations" / "007_stock_known_backfill.sql").read_text(
            encoding="utf-8"
        )
        conn.executescript(sql)
        row = conn.execute(
            "SELECT stock_known, current_stock FROM products WHERE normalized_name = 'ghost'"
        ).fetchone()
        assert int(row["current_stock"]) == 0
        assert int(row["stock_known"]) == 0
    finally:
        conn.close()


def test_almond_unknown_sale_pipeline(client):
    parse = _parse(client, "Customer bought 2 kg of almond for ₹500.").get_json()
    assert parse["intent"] == "record_sale"
    assert parse["create_product"] is True
    assert parse["needs_confirmation"] is True
    assert parse["executed"] is False
    assert parse["quantity"] == 2
    assert parse["unit"] == "kg"
    assert parse["sale_amount"] == 500
    assert client.get("/api/products").get_json()["products"] == []
    conf = client.post("/api/intents/confirm", json={"pending_id": parse["pending_id"]}).get_json()
    assert conf["executed"] is True
    products = client.get("/api/products").get_json()["products"]
    assert len(products) == 1
    assert products[0]["stock_known"] is False
    assert products[0]["current_stock"] is None
    sales = client.get("/api/sales").get_json()["sales"]
    assert len(sales) == 1
    assert sales[0]["total_amount"] == 500
    conn = get_connection()
    try:
        moves = conn.execute("SELECT COUNT(*) AS c FROM stock_movements").fetchone()["c"]
        prods = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    finally:
        conn.close()
    assert moves == 0
    assert prods == 1
    replay = client.post("/api/intents/confirm", json={"pending_id": parse["pending_id"]}).get_json()
    assert replay["replayed"] is True
    assert len(client.get("/api/products").get_json()["products"]) == 1
    assert len(client.get("/api/sales").get_json()["sales"]) == 1


def test_voice_pipeline_rice_aliases_same_id(client):
    pid = client.post(
        "/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 20}
    ).get_json()["product"]["id"]
    phrases = [
        "Customer ने 1 kg चावल लिया, 50 रुपए का।",
        "ಗ್ರಾಹಕ 1 ಕೆಜಿ ಅಕ್ಕಿ ತೆಗೆದುಕೊಂಡರು, 50 ರೂಪಾಯಿ.",
        "ग्राहकाने 1 किलो तांदूळ घेतला, 50 रुपये.",
        "Customer bought 1 kg rice for ₹50.",
    ]
    for text in phrases:
        data = _parse(client, text).get_json()
        assert data["intent"] == "record_sale", (text, data.get("message"))
        assert data.get("product"), data
        assert data["product"]["id"] == pid, (text, data.get("product_query"), data.get("create_product"))
        assert data["quantity"] == 1, text
        assert data["unit"] == "kg", text
        assert data["sale_amount"] == 50, text
        assert data["needs_confirmation"] is False, text
        assert data["executed"] is True, text
        assert data["create_product"] is False, text


def test_seed_aliases_do_not_clone_or_change_stock(client):
    first = client.post(
        "/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 12}
    ).get_json()["product"]
    pid = first["id"]
    conn = get_connection()
    try:
        before_stock = conn.execute(
            "SELECT current_stock FROM products WHERE id = ?", (pid,)
        ).fetchone()["current_stock"]
        before_sales = conn.execute("SELECT COUNT(*) AS c FROM sales").fetchone()["c"]
        from catalog import seed_aliases_for_existing

        seed_aliases_for_existing(conn)
        if conn.in_transaction:
            conn.execute("COMMIT")
        after_stock = conn.execute(
            "SELECT current_stock FROM products WHERE id = ?", (pid,)
        ).fetchone()["current_stock"]
        n_rice = conn.execute(
            "SELECT COUNT(*) AS c FROM products WHERE normalized_name = 'rice'"
        ).fetchone()["c"]
        alias_owners = conn.execute(
            """
            SELECT DISTINCT product_id FROM product_aliases
            WHERE normalized_alias IN ('चावल', 'ಅಕ್ಕಿ', 'तांदूळ', 'chawal', 'akki', 'tandul')
            """
        ).fetchall()
        after_sales = conn.execute("SELECT COUNT(*) AS c FROM sales").fetchone()["c"]
    finally:
        conn.close()
    assert after_stock == before_stock == 12 * 1_000_000
    assert n_rice == 1
    assert after_sales == before_sales == 0
    assert {int(r["product_id"]) for r in alias_owners} <= {pid}


def test_mixed_language_sale_uses_alias(client):
    pid = client.post(
        "/api/products", json={"name": "Rice", "unit": "kg", "opening_stock": 5}
    ).get_json()["product"]["id"]
    data = _parse(client, "ग्राहक ने 1 kg चावल लिया 20 रुपये का").get_json()
    assert data["intent"] == "record_sale"
    assert data["product"]["id"] == pid
    assert data["needs_confirmation"] is False
    assert data["executed"] is True
