from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from db import get_connection
from errors import ApiError
from intents.executor import confirm_action


def _count(sql: str, args: tuple = ()) -> int:
    conn = get_connection()
    try:
        return int(conn.execute(sql, args).fetchone()[0])
    finally:
        conn.close()


def _pending_status(action_id: str) -> str:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM pending_voice_actions WHERE id = ?", (action_id,)
        ).fetchone()
        return row["status"] if row else ""
    finally:
        conn.close()


def _rice(client, stock: float = 50):
    res = client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "opening_stock": stock},
    )
    assert res.status_code == 201
    pid = res.get_json()["product"]["id"]
    client.post(f"/api/products/{pid}/aliases", json={"alias": "चावल", "language": "hi"})
    client.post(f"/api/products/{pid}/aliases", json={"alias": "ಅಕ್ಕಿ", "language": "kn"})
    client.post(f"/api/products/{pid}/aliases", json={"alias": "तांदूळ", "language": "mr"})
    return pid


def _parse(client, text: str):
    return client.post("/api/intents/parse", json={"transcript": text})


def test_purchase_english(client):
    _rice(client)
    res = _parse(client, "I purchased 100 kg of rice")
    data = res.get_json()
    assert res.status_code == 200
    assert data["intent"] == "purchase_stock"
    assert data["quantity"] == 100
    assert data["unit"] == "kg"
    assert data["needs_confirmation"] is True
    assert data["pending_id"]
    stock = client.get("/api/products").get_json()["products"][0]["current_stock"]
    assert stock == 50
    conf = client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]})
    assert conf.status_code == 200
    assert conf.get_json()["executed"] is True
    stock = client.get("/api/products").get_json()["products"][0]["current_stock"]
    assert stock == 150


def test_sale_english(client):
    _rice(client, 20)
    res = _parse(client, "I sold 5 kg of rice for 200 rupees")
    data = res.get_json()
    assert data["intent"] == "record_sale"
    assert data["sale_amount"] == 200
    assert data["needs_confirmation"] is False
    assert data["executed"] is True
    sale = data["result"]["sale"]
    assert sale["total_amount"] == 200
    assert sale["payment_status"] == "unknown"
    stock = client.get("/api/products").get_json()["products"][0]["current_stock"]
    assert stock == 15


def test_check_stock(client):
    _rice(client, 12)
    res = _parse(client, "How much rice is remaining?")
    data = res.get_json()
    assert data["intent"] == "check_stock"
    assert data["executed"] is True
    assert data["needs_confirmation"] is False
    assert data["result"]["quantity"] == 12
    assert data["result"]["unit"] == "kg"


def test_languages_purchase_aliases(client):
    _rice(client, 10)
    samples = [
        "मैंने 8 किलो चावल खरीदा",
        "ನಾನು 8 ಕೆಜಿ ಅಕ್ಕಿ ಖರೀದಿಸಿದೆ",
        "मी 8 किलो तांदूळ खरेदी केली",
        "I purchased 8 kg of rice",
    ]
    for text in samples:
        res = _parse(client, text)
        data = res.get_json()
        assert data["intent"] == "purchase_stock", text
        assert data["quantity"] == 8, text
        assert data["needs_confirmation"] is True, text
        client.post("/api/intents/cancel", json={"pending_id": data["pending_id"]})


def test_unknown_product_sale(client):
    res = _parse(client, "I sold 2 kg of unicorn for 10 rupees")
    data = res.get_json()
    assert data["create_product"] is True
    assert data["needs_confirmation"] is True
    assert data["executed"] is False


def test_unknown_product_purchase_offers_create(client):
    res = _parse(client, "I purchased 3 kg of millet")
    data = res.get_json()
    assert data["create_product"] is True
    assert data["needs_confirmation"] is True
    conf = client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]})
    assert conf.status_code == 200
    names = [p["name"].lower() for p in client.get("/api/products").get_json()["products"]]
    assert "millet" in names


def test_missing_quantity(client):
    _rice(client)
    res = _parse(client, "I purchased rice")
    data = res.get_json()
    assert "quantity" in data["missing"]
    assert data["needs_confirmation"] is False


def test_missing_sale_amount(client):
    _rice(client)
    res = _parse(client, "I sold 5 kg of rice")
    data = res.get_json()
    assert "sale_amount" in data["missing"]
    assert data["needs_confirmation"] is False


def test_invalid_unit_word_not_mapped(client):
    _rice(client)
    res = _parse(client, "I purchased 5 barrels of rice")
    data = res.get_json()
    assert "unit" in data["missing"] or data.get("error_code") == "invalid_unit"


def test_incompatible_unit(client):
    _rice(client)
    res = _parse(client, "I purchased 5 l of rice")
    data = res.get_json()
    assert data["error_code"] == "incompatible_unit"
    assert data["needs_confirmation"] is False


def test_negative_quantity(client):
    res = _parse(client, "I purchased -5 kg of rice")
    data = res.get_json()
    assert data["error_code"] == "invalid_quantity"


def test_insufficient_stock_on_confirm(client):
    _rice(client, 2)
    res = _parse(client, "I sold 5 kg of rice for 100 rupees")
    data = res.get_json()
    assert data["ok"] is False
    assert data.get("error_code") == "insufficient_stock"
    assert data["executed"] is False
    stock = client.get("/api/products").get_json()["products"][0]["current_stock"]
    assert stock == 2


def test_ambiguous_product(client):
    client.post("/api/products", json={"name": "Mustard Oil", "unit": "l"})
    client.post("/api/products", json={"name": "Coconut Oil", "unit": "l"})
    res = _parse(client, "How much oil is remaining?")
    data = res.get_json()
    assert data["error_code"] == "ambiguous_product"
    assert len(data["candidates"]) == 2


def test_confirmation_required(client):
    _rice(client)
    res = _parse(client, "I purchased 1 kg of rice")
    assert res.get_json()["needs_confirmation"] is True
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == 50


def test_repeat_confirm_idempotent(client):
    _rice(client, 10)
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "I sold 1 kg of rice for 40 rupees", "session_id": "rep-sale"},
    ).get_json()
    second = client.post(
        "/api/intents/parse",
        json={"transcript": "I sold 1 kg of rice for 40 rupees", "session_id": "rep-sale"},
    ).get_json()
    assert first["executed"] is True
    assert second["replayed"] is True
    assert first["result"]["sale"]["id"] == second["result"]["sale"]["id"]
    stock = client.get("/api/products").get_json()["products"][0]["current_stock"]
    assert stock == 9


def test_cancel_pending(client):
    _rice(client)
    res = _parse(client, "I purchased 4 kg of rice")
    pid = res.get_json()["pending_id"]
    cancel = client.post("/api/intents/cancel", json={"pending_id": pid})
    assert cancel.status_code == 200
    conf = client.post("/api/intents/confirm", json={"pending_id": pid})
    assert conf.status_code == 409
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == 50


def test_new_parse_supersedes_pending(client):
    _rice(client)
    first = _parse(client, "I purchased 4 kg of rice").get_json()["pending_id"]
    _parse(client, "I purchased 2 kg of rice")
    conf = client.post("/api/intents/confirm", json={"pending_id": first})
    assert conf.status_code == 409


def test_unsupported_intent(client):
    res = _parse(client, "Play some music")
    data = res.get_json()
    assert data["intent"] in {"general_conversation", "general_question", "clarification"}
    assert data["needs_confirmation"] is False
    assert data["executed"] is False


def test_check_unknown_product(client):
    res = _parse(client, "How much quinoa is remaining?")
    assert res.get_json()["error_code"] == "unknown_product"


def test_rollback_on_confirm_failure(client, monkeypatch):
    _rice(client, 10)
    from services import stock as stock_mod

    def boom(*args, **kwargs):
        raise RuntimeError("forced")

    monkeypatch.setattr(stock_mod, "apply_stock_change", boom)
    res = _parse(client, "I purchased 3 kg of rice")
    pid = res.get_json()["pending_id"]
    conf = client.post("/api/intents/confirm", json={"pending_id": pid})
    assert conf.status_code == 500
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == 10
    assert _count("SELECT COUNT(*) FROM stock_movements WHERE movement_type = 'purchase'") == 0
    assert _pending_status(pid) == "pending"


def test_repeat_purchase_confirm_one_movement(client):
    _rice(client, 10)
    pid = _parse(client, "I purchased 5 kg of rice").get_json()["pending_id"]
    first = client.post("/api/intents/confirm", json={"pending_id": pid}).get_json()
    second = client.post("/api/intents/confirm", json={"pending_id": pid}).get_json()
    assert first["replayed"] is False
    assert second["replayed"] is True
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == 15
    assert _count("SELECT COUNT(*) FROM stock_movements WHERE movement_type = 'purchase'") == 1


def test_concurrent_purchase_confirm(client):
    _rice(client, 10)
    pid = _parse(client, "I purchased 4 kg of rice").get_json()["pending_id"]

    def run(_):
        try:
            return confirm_action(pid)
        except ApiError as exc:
            return {"ok": False, "code": exc.code, "status": exc.status}

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    oks = [r for r in results if r.get("ok")]
    assert len(oks) == 2
    assert sum(1 for r in oks if r.get("replayed")) == 1
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == 14
    assert _count("SELECT COUNT(*) FROM stock_movements WHERE movement_type = 'purchase'") == 1


def test_failure_then_retry_purchase(client, monkeypatch):
    _rice(client, 10)
    from services import stock as stock_mod

    real = stock_mod.apply_stock_change
    state = {"n": 0}

    def flaky(*args, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("forced")
        return real(*args, **kwargs)

    monkeypatch.setattr(stock_mod, "apply_stock_change", flaky)
    pid = _parse(client, "I purchased 3 kg of millet").get_json()["pending_id"]
    first = client.post("/api/intents/confirm", json={"pending_id": pid})
    assert first.status_code == 500
    names = [p["name"].lower() for p in client.get("/api/products").get_json()["products"]]
    assert "millet" not in names
    assert _pending_status(pid) == "pending"
    second = client.post("/api/intents/confirm", json={"pending_id": pid})
    assert second.status_code == 200
    names = [p["name"].lower() for p in client.get("/api/products").get_json()["products"]]
    assert "millet" in names
    millet = [p for p in client.get("/api/products").get_json()["products"] if p["name"].lower() == "millet"][0]
    assert millet["current_stock"] == 3


def test_concurrent_sale_confirm(client):
    _rice(client, 10)
    first = client.post(
        "/api/intents/parse",
        json={"transcript": "I sold 2 kg of rice for 80 rupees", "session_id": "conc-sale"},
    ).get_json()
    second = client.post(
        "/api/intents/parse",
        json={"transcript": "I sold 2 kg of rice for 80 rupees", "session_id": "conc-sale"},
    ).get_json()
    assert first["executed"] is True
    assert second["replayed"] is True
    assert first["result"]["sale"]["id"] == second["result"]["sale"]["id"]
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == 8
    assert _count("SELECT COUNT(*) FROM sales") == 1
    assert _count("SELECT COUNT(*) FROM stock_movements WHERE movement_type = 'sale'") == 1


def test_repeat_sale_one_row(client):
    _rice(client, 10)
    a = client.post(
        "/api/intents/parse",
        json={"transcript": "I sold 1 kg of rice for 40 rupees", "session_id": "one-row"},
    ).get_json()
    b = client.post(
        "/api/intents/parse",
        json={"transcript": "I sold 1 kg of rice for 40 rupees", "session_id": "one-row"},
    ).get_json()
    assert a["executed"] is True
    assert b["replayed"] is True
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == 9
    assert _count("SELECT COUNT(*) FROM sales") == 1
    assert _count("SELECT COUNT(*) FROM stock_movements WHERE movement_type = 'sale'") == 1


def _assert_slots(data, *, intent, product, qty, unit, amount=None):
    assert data["intent"] == intent
    assert data["product_query"] == product
    assert data["quantity"] == qty
    assert data["unit"] == unit
    if amount is None:
        assert data["sale_amount"] in (None, amount)
    else:
        assert data["sale_amount"] == amount
    assert "customer" not in (data["product_query"] or "")


def test_spoken_english_customer_sale_not_purchase(client):
    _rice(client, 20)
    res = _parse(client, "A customer bought 1 kg of rice for rupees 50.")
    data = res.get_json()
    _assert_slots(data, intent="record_sale", product="rice", qty=1, unit="kg", amount=50)
    assert data["create_product"] is False
    names = [p["name"].lower() for p in client.get("/api/products").get_json()["products"]]
    assert "customer rice" not in names
    if data.get("pending_id"):
        client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]})
    names = [p["name"].lower() for p in client.get("/api/products").get_json()["products"]]
    assert "customer rice" not in names
    assert all("customer" not in n for n in names)


def test_spoken_english_shop_purchase(client):
    _rice(client, 10)
    data = _parse(client, "I purchased 10 kg rice for my shop.").get_json()
    _assert_slots(data, intent="purchase_stock", product="rice", qty=10, unit="kg")
    assert data["create_product"] is False


def test_spoken_english_i_sold(client):
    _rice(client, 20)
    data = _parse(client, "I sold 5 kg rice for 200 rupees.").get_json()
    _assert_slots(data, intent="record_sale", product="rice", qty=5, unit="kg", amount=200)


def test_spoken_hindi_customer_took(client):
    _rice(client, 20)
    data = _parse(client, "एक customer ने 1 किलो चावल लिया, 50 रुपए का।").get_json()
    _assert_slots(data, intent="record_sale", product="चावल", qty=1, unit="kg", amount=50)
    assert data["create_product"] is False


def test_spoken_hindi_shop_purchase(client):
    _rice(client, 10)
    data = _parse(client, "मैंने दुकान के लिए 10 किलो चावल खरीदा।").get_json()
    _assert_slots(data, intent="purchase_stock", product="चावल", qty=10, unit="kg")


def test_spoken_hindi_i_sold(client):
    _rice(client, 20)
    data = _parse(client, "मैंने 5 किलो चावल 200 रुपए में बेचा।").get_json()
    _assert_slots(data, intent="record_sale", product="चावल", qty=5, unit="kg", amount=200)


def test_spoken_kannada_customer_and_shop(client):
    _rice(client, 20)
    sale = _parse(client, "ಒಬ್ಬ ಗ್ರಾಹಕ 1 ಕೆಜಿ ಅಕ್ಕಿ ತೆಗೆದುಕೊಂಡ, 50 ರೂಪಾಯಿ.").get_json()
    _assert_slots(sale, intent="record_sale", product="ಅಕ್ಕಿ", qty=1, unit="kg", amount=50)
    buy = _parse(client, "ನಾನು ಅಂಗಡಿಗೆ 10 ಕೆಜಿ ಅಕ್ಕಿ ಖರೀದಿಸಿದೆ.").get_json()
    _assert_slots(buy, intent="purchase_stock", product="ಅಕ್ಕಿ", qty=10, unit="kg")
    sold = _parse(client, "ನಾನು 5 ಕೆಜಿ ಅಕ್ಕಿ 200 ರೂಪಾಯಿಗೆ ಮಾರಿದೆ.").get_json()
    _assert_slots(sold, intent="record_sale", product="ಅಕ್ಕಿ", qty=5, unit="kg", amount=200)


def test_spoken_marathi_customer_and_shop(client):
    _rice(client, 20)
    sale = _parse(client, "एका ग्राहकाने 1 किलो तांदूळ घेतले, 50 रुपये.").get_json()
    _assert_slots(sale, intent="record_sale", product="तांदूळ", qty=1, unit="kg", amount=50)
    buy = _parse(client, "मी दुकानासाठी 10 किलो तांदूळ खरेदी केली.").get_json()
    _assert_slots(buy, intent="purchase_stock", product="तांदूळ", qty=10, unit="kg")
    sold = _parse(client, "मी 5 किलो तांदूळ 200 रुपयांना विकले.").get_json()
    _assert_slots(sold, intent="record_sale", product="तांदूळ", qty=5, unit="kg", amount=200)


def test_english_sold_at_does_not_keep_at(client):
    _rice(client, 20)
    data = _parse(client, "1 kg of rice is sold at 50 rupees.").get_json()
    _assert_slots(data, intent="record_sale", product="rice", qty=1, unit="kg", amount=50)
    assert data["create_product"] is False
    assert data["product"]["name"].lower() == "rice"
    assert "rice at" not in (data["product_query"] or "")
    names = [p["name"].lower() for p in client.get("/api/products").get_json()["products"]]
    assert "rice at" not in names
    if data.get("pending_id"):
        client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]})
    names = [p["name"].lower() for p in client.get("/api/products").get_json()["products"]]
    assert names == ["rice"]


def test_english_sold_for_and_customer_milk(client):
    _rice(client, 20)
    sold = _parse(client, "I sold 2 kg of rice for 100 rupees.").get_json()
    _assert_slots(sold, intent="record_sale", product="rice", qty=2, unit="kg", amount=100)
    assert sold["product"]["name"].lower() == "rice"
    milk = client.post(
        "/api/products",
        json={"name": "Milk", "unit": "l", "opening_stock": 20},
    )
    assert milk.status_code == 201
    bought = _parse(client, "Customer bought 1 litre of milk for 60 rupees.").get_json()
    _assert_slots(bought, intent="record_sale", product="milk", qty=1, unit="l", amount=60)
    assert bought["product"]["name"].lower() == "milk"
    buy = _parse(client, "I purchased 10 kg of rice for my shop.").get_json()
    _assert_slots(buy, intent="purchase_stock", product="rice", qty=10, unit="kg")
    assert buy["create_product"] is False


def test_never_creates_customer_rice_product(client):
    data = _parse(client, "A customer bought 1 kg of rice for rupees 50.").get_json()
    assert data["intent"] == "record_sale"
    assert data["product_query"] == "rice"
    names = [p["name"].lower() for p in client.get("/api/products").get_json()["products"]]
    assert names == []
    assert "customer rice" not in names


def test_expired_pending_not_executed(client, monkeypatch):
    monkeypatch.setattr("config.Config.INTENT_PENDING_TTL_SECONDS", 1)
    monkeypatch.setattr("intents.executor.Config.INTENT_PENDING_TTL_SECONDS", 1)
    _rice(client, 10)
    pid = _parse(client, "I purchased 2 kg of rice").get_json()["pending_id"]
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE pending_voice_actions SET created_at = '2000-01-01T00:00:00+05:30' WHERE id = ?",
            (pid,),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    conf = client.post("/api/intents/confirm", json={"pending_id": pid})
    assert conf.status_code == 409
    assert client.get("/api/products").get_json()["products"][0]["current_stock"] == 10
    assert _pending_status(pid) == "expired"
