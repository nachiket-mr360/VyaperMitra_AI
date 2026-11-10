from __future__ import annotations

from intents.parser import parse_transcript


def _sugar(client):
    res = client.post(
        "/api/products",
        json={"name": "Sugar", "unit": "kg", "opening_stock": 50},
    )
    assert res.status_code == 201
    pid = res.get_json()["product"]["id"]
    client.post(f"/api/products/{pid}/aliases", json={"alias": "शुगर", "language": "hi"})
    return pid


def _parse(client, text, session_id):
    return client.post(
        "/api/intents/parse",
        json={"transcript": text, "session_id": session_id},
    ).get_json()


def test_assi_rupayon_parses_amount_80():
    d = parse_transcript("एक कस्टमर ने दो किलो शुगर लिया, अस्सी रुपयों का।")
    assert d.intent == "record_sale"
    assert d.quantity == 2
    assert d.unit == "kg"
    assert d.sale_amount == 80
    assert "sale_amount" not in (d.missing or [])


def test_digit_80_rupees_parses():
    d = parse_transcript("एक ग्राहक ने 2 किलो शुगर 80 रुपये में खरीदी।")
    assert d.intent == "record_sale"
    assert d.quantity == 2
    assert d.unit == "kg"
    assert d.sale_amount == 80


def test_missing_amount_asks_once(client):
    _sugar(client)
    data = _parse(client, "एक कस्टमर ने दो किलो शुगर लिया।", "amt-c")
    assert data["intent"] == "record_sale"
    assert data["executed"] is False
    assert "sale_amount" in data["missing"]
    assert "कितने रुपये" in (data.get("reply_text") or data["message"])


def test_followup_eighty_rupees_stt(client):
    _sugar(client)
    sid = "amt-eighty"
    first = _parse(client, "एक कस्टमर ने दो किलो शुगर लिया।", sid)
    assert "sale_amount" in first["missing"]
    second = _parse(client, "एटी रूपीज का।", sid)
    assert second["intent"] == "record_sale"
    assert second.get("sale_amount") == 80
    assert second["quantity"] == 2
    assert second["executed"] is True or second.get("needs_confirmation") is True
    assert second["executed"] is not False or second.get("needs_confirmation")


def test_followup_sath_rupees(client):
    _sugar(client)
    sid = "amt-sath"
    _parse(client, "एक कस्टमर ने दो किलो शुगर लिया।", sid)
    second = _parse(client, "साठ रुपये।", sid)
    assert second.get("sale_amount") == 60
    assert second["quantity"] == 2
    assert second["executed"] is True or second.get("needs_confirmation") is True


def test_unclear_followup_does_not_execute(client):
    _sugar(client)
    sid = "amt-unclear"
    first = _parse(client, "एक कस्टमर ने दो किलो शुगर लिया।", sid)
    ask = first.get("reply_text") or first["message"]
    second = _parse(client, "ओंभी।", sid)
    assert second["executed"] is False
    assert "sale_amount" in (second.get("missing") or [])
    reply = second.get("reply_text") or second["message"]
    assert reply != ask
    assert second.get("result") is None


def test_full_sentence_commits_80(client):
    _sugar(client)
    data = _parse(
        client,
        "एक कस्टमर ने दो किलो शुगर लिया, अस्सी रुपयों का।",
        "amt-full",
    )
    assert data["intent"] == "record_sale"
    assert data["sale_amount"] == 80
    assert data["quantity"] == 2
    assert data["executed"] is True
    bills = client.get("/api/sales").get_json()["sales"]
    assert len(bills) == 1
    assert bills[0]["total_amount"] == 80


def test_ek_sau_bees():
    d = parse_transcript("एक कस्टमर ने एक किलो चावल लिया एक सौ बीस रुपये का")
    assert d.sale_amount == 120
    assert d.quantity == 1
