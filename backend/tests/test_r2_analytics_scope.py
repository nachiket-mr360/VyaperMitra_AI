from __future__ import annotations

from datetime import timedelta

from timeutil import business_date_str, now_business


def _rice(client, stock=80):
    return client.post(
        "/api/products",
        json={"name": "Rice", "unit": "kg", "low_stock_threshold": 1, "opening_stock": stock},
    ).get_json()["product"]


def _dal(client, stock=80):
    return client.post(
        "/api/products",
        json={"name": "Dal", "unit": "kg", "low_stock_threshold": 1, "opening_stock": stock},
    ).get_json()["product"]


def _sell(client, product, qty, total, key, day=None):
    body = {
        "idempotency_key": key,
        "items": [{"product_id": product["id"], "quantity": qty, "line_total": total}],
    }
    if day:
        body["transaction_date"] = day
    return client.post("/api/sales", json=body).get_json()["sale"]


def _mutate(client, path, body, session="sess-r2"):
    body = {**body, "session_id": session}
    proposed = client.post(path, json=body)
    assert proposed.status_code == 202, proposed.get_json()
    confirmed = client.post(
        "/api/intents/confirm",
        json={"pending_id": proposed.get_json()["pending_id"], "session_id": session},
    )
    assert confirmed.status_code == 200, confirmed.get_json()
    return confirmed.get_json()


def _kpi(viz, label):
    for k in viz.get("kpis") or []:
        if k.get("label") == label:
            return k.get("value")
    return None


def test_overview_kpis_match_period_not_today(client):
    rice = _rice(client)
    today = business_date_str()
    yest = (now_business().date() - timedelta(days=1)).isoformat()
    older = (now_business().date() - timedelta(days=3)).isoformat()
    _sell(client, rice, 2, 400, "r2-old", older)
    _sell(client, rice, 1, 485, "r2-yest", yest)

    dash = client.get("/api/analytics/dashboard").get_json()
    assert dash["today"]["total_amount"] == 0
    assert dash["period"]["total_amount"] == 885
    assert dash["period"]["transactions"] == 2
    trend_sum = sum(float(r["total_amount"]) for r in dash["trend"])
    assert trend_sum == dash["period"]["total_amount"]

    voice = client.post("/api/intents/parse", json={"transcript": "How is my business doing?"}).get_json()
    assert voice["intent"] == "check_analytics"
    assert voice["result"]["topic"] == "overview"
    assert voice["result"]["today"]["total_amount"] == 0
    assert voice["result"]["total_amount"] == dash["period"]["total_amount"]
    assert voice["result"]["transactions"] == dash["period"]["transactions"]
    viz = voice["visualization"]
    assert viz
    sales_kpi = _kpi(viz, "Recorded sales")
    bills_kpi = _kpi(viz, "Bills")
    point_sum = sum(float(p["value"]) for p in viz["points"])
    assert sales_kpi == dash["period"]["total_amount"]
    assert bills_kpi == dash["period"]["transactions"]
    assert point_sum == sales_kpi
    assert not (sales_kpi == 0 and point_sum != 0)
    reply = voice.get("reply_text") or voice.get("message") or ""
    assert "885" in reply.replace(",", "")
    assert "Today separately" in reply or "आज अलग" in reply or "ಇಂದು ಪ್ರತ್ಯೇಕ" in reply or "आज वेगळे" in reply

    today_q = client.post("/api/intents/parse", json={"transcript": "How much did I sell today?"}).get_json()
    assert today_q["result"]["topic"] == "sales_summary"
    assert today_q["result"]["total_amount"] == 0
    today_reply = today_q.get("reply_text") or today_q.get("message") or ""
    assert "885" not in today_reply.replace(",", "")


def test_lifecycle_nets_in_period_and_products(client):
    rice = _rice(client)
    dal = _dal(client)
    today = business_date_str()
    yest = (now_business().date() - timedelta(days=1)).isoformat()
    d2 = (now_business().date() - timedelta(days=2)).isoformat()

    corrected = _sell(client, rice, 5, 200, "r2-corr", yest)
    key = corrected["lines"][0]["line_key"]
    _mutate(client, f"/api/sales/{corrected['id']}/corrections", {"line_key": key, "quantity": 3})

    returned = _sell(client, dal, 4, 400, "r2-ret", d2)
    rkey = returned["lines"][0]["line_key"]
    _mutate(client, f"/api/sales/{returned['id']}/returns", {"line_key": rkey, "quantity": 1})

    cancelled = _sell(client, rice, 2, 100, "r2-can", today)
    _mutate(client, f"/api/sales/{cancelled['id']}/cancel", {})

    _sell(client, rice, 1, 50, "r2-keep", d2)

    dash = client.get("/api/analytics/dashboard").get_json()
    voice = client.post("/api/intents/parse", json={"transcript": "Show my sales this week."}).get_json()
    assert voice["result"]["topic"] in {"sales_summary", "sales_trend", "overview"}
    period_amt = dash["period"]["total_amount"]
    period_tx = dash["period"]["transactions"]
    trend_sum = sum(float(r["total_amount"]) for r in dash["trend"])
    assert trend_sum == period_amt
    assert voice["result"]["total_amount"] == period_amt
    viz = voice["visualization"]
    assert sum(float(p["value"]) for p in viz["points"]) == _kpi(viz, "Recorded sales")
    assert _kpi(viz, "Bills") == period_tx
    assert dash["today"]["total_amount"] == 0

    products = client.post("/api/intents/parse", json={"transcript": "What did I sell this week?"}).get_json()
    rows = (products.get("result") or {}).get("by_product") or []
    prod_sum = sum(float(r["amount"]) for r in rows)
    assert prod_sum == period_amt

    detail_c = client.get(f"/api/sales/{cancelled['id']}").get_json()["sale"]
    assert detail_c["status"] == "cancelled"
    assert detail_c["financials"]["net_recorded"] == 0


def test_active_bills_exclude_fully_cancelled(client):
    rice = _rice(client, 200)
    dal = _dal(client, 200)
    today = business_date_str()
    yest = (now_business().date() - timedelta(days=1)).isoformat()
    d2 = (now_business().date() - timedelta(days=2)).isoformat()

    _sell(client, rice, 1, 10, "r2b-a1", today)
    _sell(client, rice, 1, 20, "r2b-a2", yest)
    _sell(client, dal, 1, 30, "r2b-a3", d2)

    returned = _sell(client, dal, 4, 400, "r2b-ret", yest)
    _mutate(client, f"/api/sales/{returned['id']}/returns", {"line_key": returned["lines"][0]["line_key"], "quantity": 1})

    corrected = _sell(client, rice, 5, 200, "r2b-corr", d2)
    _mutate(client, f"/api/sales/{corrected['id']}/corrections", {"line_key": corrected["lines"][0]["line_key"], "quantity": 3})

    cancelled = _sell(client, rice, 2, 100, "r2b-can", today)
    _mutate(client, f"/api/sales/{cancelled['id']}/cancel", {})

    dash = client.get("/api/analytics/dashboard").get_json()
    assert dash["period"]["transactions"] == 5
    assert dash["period"]["cancelled_bills"] == 1
    assert sum(int(r["transactions"]) for r in dash["trend"]) == 5
    assert sum(int(r.get("cancelled_bills") or 0) for r in dash["trend"]) == 1
    prod_sum = sum(float(r["amount"]) for r in dash["by_product"])
    assert prod_sum == dash["period"]["total_amount"]
    assert dash["today"]["transactions"] == 1
    assert dash["today"]["cancelled_bills"] == 1

    voice = client.post("/api/intents/parse", json={"transcript": "How is my business doing?"}).get_json()
    assert voice["result"]["transactions"] == 5
    assert (voice["result"].get("period") or {}).get("cancelled_bills") == 1
    assert _kpi(voice["visualization"], "Bills") == 5
    assert _kpi(voice["visualization"], "Cancelled bills") == 1
    week = client.post("/api/intents/parse", json={"transcript": "Show my sales this week."}).get_json()
    assert week["result"]["transactions"] == 5
    assert _kpi(week["visualization"], "Bills") == 5


def test_business_advice_has_no_sales_chart(client):
    rice = _rice(client)
    _sell(client, rice, 1, 80, "r2-adv")
    adv = client.post("/api/intents/parse", json={"transcript": "How can I improve my sales?"}).get_json()
    assert adv["intent"] == "business_advice"
    assert adv.get("visualization") in (None, {})
