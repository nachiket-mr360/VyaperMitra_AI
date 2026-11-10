from __future__ import annotations

from datetime import timedelta

from db import get_connection
from timeutil import now_business


def test_reminder_crud_and_timezone(client):
    today = now_business().date().isoformat()
    res = client.post(
        "/api/reminders",
        json={"title": "Call supplier", "due_date": today, "due_time": "10:00"},
    )
    assert res.status_code == 201
    rid = res.get_json()["reminder"]["id"]
    assert res.get_json()["reminder"]["due_date"] == today
    listed = client.get("/api/reminders?status=open").get_json()["reminders"]
    assert any(r["id"] == rid for r in listed)
    patched = client.patch(
        f"/api/reminders/{rid}",
        json={"title": "Call rice supplier", "due_time": "11:00"},
    ).get_json()["reminder"]
    assert patched["title"] == "Call rice supplier"
    assert patched["due_time"] == "11:00"
    bad = client.post("/api/reminders", json={"title": "x", "due_date": "not-a-date"})
    assert bad.status_code == 400
    client.delete(f"/api/reminders/{rid}")
    gone = client.get("/api/reminders").get_json()["reminders"]
    assert gone == []


def test_overdue_and_recurring(client):
    past = (now_business().date() - timedelta(days=2)).isoformat()
    row = client.post(
        "/api/reminders",
        json={"title": "Pay bill", "due_date": past, "due_time": "09:00"},
    ).get_json()["reminder"]
    assert row["overdue"] is True
    brief = client.get("/api/reminders/briefing").get_json()
    assert brief["timezone"] == "Asia/Kolkata"
    assert any(r["id"] == row["id"] for r in brief["overdue"])
    assert "not" in brief["notify_note"].lower() or "open" in brief["notify_note"].lower()

    today = now_business().date().isoformat()
    daily = client.post(
        "/api/reminders",
        json={
            "title": "Check milk",
            "due_date": today,
            "due_time": "09:00",
            "recurrence": "daily",
        },
    ).get_json()["reminder"]
    done = client.post(f"/api/reminders/{daily['id']}/complete").get_json()["reminder"]
    assert done["status"] == "open"
    assert done["due_date"] != today
    weekly = client.post(
        "/api/reminders",
        json={
            "title": "Weekly stock",
            "due_date": today,
            "due_time": "08:00",
            "recurrence": "weekly",
        },
    ).get_json()["reminder"]
    week_done = client.post(f"/api/reminders/{weekly['id']}/complete").get_json()["reminder"]
    assert week_done["due_date"] == (now_business().date() + timedelta(days=7)).isoformat()
    bad_rec = client.post(
        "/api/reminders",
        json={"title": "x", "due_date": today, "recurrence": "yearly"},
    )
    assert bad_rec.status_code == 400


def test_monthly_recurrence_preserves_intended_day(client):
    jan = client.post(
        "/api/reminders",
        json={
            "title": "Rent",
            "due_date": "2026-01-31",
            "due_time": "09:00",
            "recurrence": "monthly",
        },
    ).get_json()["reminder"]
    assert jan["month_day"] == 31
    feb = client.post(f"/api/reminders/{jan['id']}/complete").get_json()["reminder"]
    assert feb["due_date"] == "2026-02-28"
    assert feb["status"] == "open"
    assert feb["month_day"] == 31
    mar = client.post(f"/api/reminders/{jan['id']}/complete").get_json()["reminder"]
    assert mar["due_date"] == "2026-03-31"
    leap = client.post(
        "/api/reminders",
        json={
            "title": "Leap rent",
            "due_date": "2024-01-31",
            "due_time": "09:00",
            "recurrence": "monthly",
        },
    ).get_json()["reminder"]
    leap_feb = client.post(f"/api/reminders/{leap['id']}/complete").get_json()["reminder"]
    assert leap_feb["due_date"] == "2024-02-29"
    leap_mar = client.post(f"/api/reminders/{leap['id']}/complete").get_json()["reminder"]
    assert leap_mar["due_date"] == "2024-03-31"


def test_overdue_listed_beside_many_upcoming(client):
    past = (now_business().date() - timedelta(days=3)).isoformat()
    overdue = client.post(
        "/api/reminders",
        json={"title": "Overdue one", "due_date": past, "due_time": "09:00"},
    ).get_json()["reminder"]
    start = now_business().date() + timedelta(days=2)
    for i in range(12):
        day = (start + timedelta(days=i)).isoformat()
        client.post(
            "/api/reminders",
            json={"title": f"Future {i}", "due_date": day, "due_time": "10:00"},
        )
    brief = client.get("/api/reminders/briefing").get_json()
    assert any(r["id"] == overdue["id"] for r in brief["overdue"])
    open_rows = client.get("/api/reminders?status=open").get_json()["reminders"]
    assert any(r["id"] == overdue["id"] and r["overdue"] is True for r in open_rows)
    assert len(open_rows) >= 13
    assert brief["upcoming_limit"] == 8
    assert brief["upcoming_total"] >= 12
    assert len(brief["upcoming"]) == 8


def test_monthly_days_29_30_31(client):
    cases = [
        ("2026-01-29", "2026-02-28", "2026-03-29"),
        ("2026-01-30", "2026-02-28", "2026-03-30"),
        ("2026-01-31", "2026-02-28", "2026-03-31"),
        ("2024-01-29", "2024-02-29", "2024-03-29"),
        ("2024-01-30", "2024-02-29", "2024-03-30"),
        ("2024-01-31", "2024-02-29", "2024-03-31"),
    ]
    for start, feb, mar in cases:
        row = client.post(
            "/api/reminders",
            json={
                "title": f"Day {start}",
                "due_date": start,
                "due_time": "09:00",
                "recurrence": "monthly",
            },
        ).get_json()["reminder"]
        first = client.post(f"/api/reminders/{row['id']}/complete").get_json()["reminder"]
        assert first["due_date"] == feb, (start, first["due_date"])
        second = client.post(f"/api/reminders/{row['id']}/complete").get_json()["reminder"]
        assert second["due_date"] == mar, (start, second["due_date"])


def test_note_search_multilingual(client):
    client.post("/api/notes", json={"body": "Rice delivery tomorrow"})
    client.post("/api/notes", json={"body": "चावल कल आएगा"})
    client.post("/api/notes", json={"body": "ನಾಳೆ ಅಕ್ಕಿ ಬರುತ್ತದೆ"})
    client.post("/api/notes", json={"body": "उद्या तांदूळ येणार आहे"})
    all_notes = client.get("/api/notes").get_json()["notes"]
    assert len(all_notes) == 4
    rice = client.get("/api/notes?q=rice").get_json()["notes"]
    assert len(rice) == 1
    assert rice[0]["body"] == "Rice delivery tomorrow"
    hi = client.get("/api/notes?q=चावल").get_json()["notes"]
    assert hi[0]["body"] == "चावल कल आएगा"
    kn = client.get("/api/notes?q=ಅಕ್ಕಿ").get_json()["notes"]
    assert kn[0]["body"] == "ನಾಳೆ ಅಕ್ಕಿ ಬರುತ್ತದೆ"
    mr = client.get("/api/notes?q=तांदूळ").get_json()["notes"]
    assert mr[0]["body"] == "उद्या तांदूळ येणार आहे"
    empty = client.get("/api/notes?q=").get_json()["notes"]
    assert len(empty) == 4
    case = client.get("/api/notes?q=RICE").get_json()["notes"]
    assert len(case) == 1


def test_kn_mr_list_and_delete_voice(client):
    today = now_business().date().isoformat()
    client.post("/api/reminders", json={"title": "Order rice", "due_date": today, "due_time": "10:00"})
    client.post("/api/notes", json={"body": "ಅಕ್ಕಿ ಬರುತ್ತದೆ"})
    client.post("/api/notes", json={"body": "तांदूळ येणार"})
    for phrase in ("ನೆನಪುಗಳನ್ನು ತೋರಿಸು", "ರಿಮೈಂಡರ್ ತೋರಿಸು", "आठवणी दाखवा", "रिमाइंडर दाखवा"):
        data = client.post("/api/intents/parse", json={"transcript": phrase}).get_json()
        assert data["intent"] == "list_reminders", phrase
        assert data["executed"] is True
        assert data["needs_confirmation"] is False
    for phrase in ("ಟಿಪ್ಪಣಿಗಳನ್ನು ತೋರಿಸು", "ನೋಟ್ ತೋರಿಸು", "नोंदी दाखवा", "नोट दाखवा"):
        data = client.post("/api/intents/parse", json={"transcript": phrase}).get_json()
        assert data["intent"] == "list_notes", phrase
        assert data["executed"] is True
    parsed = client.post(
        "/api/intents/parse",
        json={"transcript": "Order rice ರಿಮೈಂಡರ್ ಅಳಿಸು"},
    ).get_json()
    assert parsed["intent"] == "delete_reminder"
    assert parsed["needs_confirmation"] is True
    assert parsed["executed"] is False
    assert len(client.get("/api/reminders").get_json()["reminders"]) == 1
    client.post("/api/intents/confirm", json={"pending_id": parsed["pending_id"]})
    assert client.get("/api/reminders").get_json()["reminders"] == []
    client.post("/api/reminders", json={"title": "Pay bill", "due_date": today, "due_time": "09:00"})
    mr_del = client.post(
        "/api/intents/parse",
        json={"transcript": "Pay bill आठवण काढून टाक"},
    ).get_json()
    assert mr_del["intent"] == "delete_reminder"
    assert mr_del["needs_confirmation"] is True
    client.post("/api/intents/confirm", json={"pending_id": mr_del["pending_id"]})
    assert client.get("/api/reminders").get_json()["reminders"] == []
    kn_note = client.post(
        "/api/intents/parse",
        json={"transcript": "ಅಕ್ಕಿ ನೋಟ್ ಅಳಿಸು"},
    ).get_json()
    assert kn_note["intent"] == "delete_note"
    assert kn_note["needs_confirmation"] is True
    assert kn_note["executed"] is False
    client.post("/api/intents/confirm", json={"pending_id": kn_note["pending_id"]})
    bodies = [n["body"] for n in client.get("/api/notes").get_json()["notes"]]
    assert "ಅಕ್ಕಿ ಬರುತ್ತದೆ" not in bodies
    mr_note = client.post(
        "/api/intents/parse",
        json={"transcript": "तांदूळ नोंद काढून टाक"},
    ).get_json()
    assert mr_note["intent"] == "delete_note"
    assert mr_note["needs_confirmation"] is True
    client.post("/api/intents/confirm", json={"pending_id": mr_note["pending_id"]})
    assert client.get("/api/notes").get_json()["notes"] == []
    vague = client.post("/api/intents/parse", json={"transcript": "ರಿಮೈಂಡರ್ ಅಳಿಸು"}).get_json()
    assert vague["intent"] == "delete_reminder"
    assert vague.get("missing") == ["title"] or vague.get("error_code") in {
        "not_found",
        "ambiguous_reminder",
    }


def test_notes_crud_not_sales(client):
    res = client.post("/api/notes", json={"body": "Ramesh owes 500 rupees"})
    assert res.status_code == 201
    nid = res.get_json()["note"]["id"]
    client.patch(f"/api/notes/{nid}", json={"body": "Ramesh owes 400 rupees"})
    notes = client.get("/api/notes").get_json()["notes"]
    assert notes[0]["body"].startswith("Ramesh")
    sales = client.get("/api/sales").get_json()
    assert sales.get("sales", sales.get("items", [])) == [] or len(sales.get("sales", [])) == 0
    client.delete(f"/api/notes/{nid}")
    assert client.get("/api/notes").get_json()["notes"] == []


def test_voice_reminder_needs_confirm(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Remind me to call the supplier tomorrow at 10 AM."},
    ).get_json()
    assert data["intent"] == "create_reminder"
    assert data["needs_confirmation"] is True
    assert data["executed"] is False
    assert client.get("/api/reminders").get_json()["reminders"] == []
    conf = client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]}).get_json()
    assert conf["executed"] is True
    assert conf["result"]["reminder"]["title"].lower().find("supplier") >= 0
    again = client.post("/api/intents/confirm", json={"pending_id": data["pending_id"]}).get_json()
    assert again["replayed"] is True
    assert len(client.get("/api/reminders").get_json()["reminders"]) == 1


def test_voice_reminder_ambiguous_time(client):
    data = client.post(
        "/api/intents/parse",
        json={"transcript": "Remind me to order rice soon"},
    ).get_json()
    assert data["intent"] == "create_reminder"
    assert "date" in data["missing"]
    assert data["pending_id"] is None


def test_multilingual_reminder_parse(client):
    samples = [
        "Remind me to order rice on Monday.",
        "Remind me to pay the electricity bill on the 15th.",
        "Remind me to check milk stock every morning at 9 AM.",
        "कल सप्लायर को कॉल करने याद दिलाओ सुबह 10 बजे",
        "ನಾಳೆ ಅಕ್ಕಿ ಆರ್ಡರ್ ಮಾಡಲು ನೆನಪಿಸು",
        "उद्या दूध तपासायला आठवण दे",
    ]
    for phrase in samples:
        data = client.post("/api/intents/parse", json={"transcript": phrase}).get_json()
        assert data["intent"] == "create_reminder", phrase


def test_voice_delete_reminder_confirm(client):
    today = now_business().date().isoformat()
    client.post("/api/reminders", json={"title": "Order rice", "due_date": today, "due_time": "10:00"})
    parsed = client.post(
        "/api/intents/parse",
        json={"transcript": "Delete reminder order rice"},
    ).get_json()
    assert parsed["needs_confirmation"] is True
    assert len(client.get("/api/reminders").get_json()["reminders"]) == 1
    client.post("/api/intents/confirm", json={"pending_id": parsed["pending_id"]})
    assert client.get("/api/reminders").get_json()["reminders"] == []


def test_multilingual_call_supplier_titles(client):
    tomorrow = (now_business().date() + timedelta(days=1)).isoformat()
    samples = [
        "Remind me to call the supplier tomorrow at 10 AM.",
        "कल सुबह 10 बजे मुझे सप्लायर को फोन करने की याद दिलाना।",
        "ನಾಳೆ ಬೆಳಿಗ್ಗೆ 10 ಗಂಟೆಗೆ ನನಗೆ ಸಪ್ಲೈಯರ್‌ಗೆ ಕರೆ ಮಾಡಲು ನೆನಪಿಸು.",
        "उद्या सकाळी १० वाजता मला सप्लायरला फोन करण्याची आठवण करून दे.",
    ]
    for phrase in samples:
        data = client.post("/api/intents/parse", json={"transcript": phrase}).get_json()
        assert data["intent"] == "create_reminder", phrase
        assert data["title"] == "Call supplier", (phrase, data.get("title"))
        assert data["due_date"] == tomorrow, phrase
        assert data["due_time"] == "10:00", (phrase, data.get("due_time"))
        assert data["needs_confirmation"] is True
        assert data["executed"] is False


def test_note_body_keeps_date_words(client):
    cases = [
        ("Note that rice will arrive tomorrow.", "rice will arrive tomorrow"),
        ("नोट लिखो कि चावल कल आएगा", "चावल कल आएगा"),
        ("ನಾಳೆ ಅಕ್ಕಿ ಬರುತ್ತದೆ ಎಂದು ನೋಟ್ ಮಾಡು", "ನಾಳೆ ಅಕ್ಕಿ ಬರುತ್ತದೆ"),
        ("उद्या तांदूळ येणार आहे अशी नोंद कर", "उद्या तांदूळ येणार आहे"),
    ]
    for phrase, body in cases:
        data = client.post("/api/intents/parse", json={"transcript": phrase}).get_json()
        assert data["intent"] == "create_note", phrase
        assert data["body"] == body, (phrase, data.get("body"))
        assert data["needs_confirmation"] is True
        assert data["executed"] is False


def test_voice_complete_reminder_needs_confirm(client):
    today = now_business().date().isoformat()
    rid = client.post(
        "/api/reminders",
        json={"title": "Order rice", "due_date": today, "due_time": "10:00"},
    ).get_json()["reminder"]["id"]
    parsed = client.post(
        "/api/intents/parse",
        json={"transcript": "Complete reminder order rice"},
    ).get_json()
    assert parsed["intent"] == "complete_reminder"
    assert parsed["needs_confirmation"] is True
    assert parsed["executed"] is False
    assert parsed["pending_id"]
    still = client.get(f"/api/reminders").get_json()["reminders"]
    assert still[0]["status"] == "open"
    conf = client.post("/api/intents/confirm", json={"pending_id": parsed["pending_id"]}).get_json()
    assert conf["executed"] is True
    assert conf["replayed"] is False
    assert conf["result"]["reminder"]["id"] == rid
    assert conf["result"]["reminder"]["status"] == "completed"
    again = client.post("/api/intents/confirm", json={"pending_id": parsed["pending_id"]}).get_json()
    assert again["replayed"] is True
    completed = [r for r in client.get("/api/reminders").get_json()["reminders"] if r["id"] == rid]
    assert len(completed) == 1
    assert completed[0]["status"] == "completed"


def test_voice_complete_reminder_cancel_and_expire(client, monkeypatch):
    today = now_business().date().isoformat()
    client.post(
        "/api/reminders",
        json={"title": "Pay bill", "due_date": today, "due_time": "09:00"},
    )
    parsed = client.post(
        "/api/intents/parse",
        json={"transcript": "Complete reminder pay bill"},
    ).get_json()
    pid = parsed["pending_id"]
    cancel = client.post("/api/intents/cancel", json={"pending_id": pid})
    assert cancel.status_code == 200
    conf = client.post("/api/intents/confirm", json={"pending_id": pid})
    assert conf.status_code == 409
    open_rows = client.get("/api/reminders?status=open").get_json()["reminders"]
    assert any(r["title"] == "Pay bill" and r["status"] == "open" for r in open_rows)

    parsed2 = client.post(
        "/api/intents/parse",
        json={"transcript": "Complete reminder pay bill"},
    ).get_json()
    pid2 = parsed2["pending_id"]
    monkeypatch.setattr("config.Config.INTENT_PENDING_TTL_SECONDS", 1)
    monkeypatch.setattr("intents.executor.Config.INTENT_PENDING_TTL_SECONDS", 1)
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE pending_voice_actions SET created_at = '2000-01-01T00:00:00+05:30' WHERE id = ?",
            (pid2,),
        )
        conn.execute("COMMIT")
    finally:
        conn.close()
    expired = client.post("/api/intents/confirm", json={"pending_id": pid2})
    assert expired.status_code == 409
    still_open = client.get("/api/reminders?status=open").get_json()["reminders"]
    assert any(r["title"] == "Pay bill" and r["status"] == "open" for r in still_open)


def test_note_voice_does_not_create_sale(client):
    parsed = client.post(
        "/api/intents/parse",
        json={"transcript": "Note that customer Ramesh owes 500 rupees"},
    ).get_json()
    assert parsed["intent"] == "create_note"
    client.post("/api/intents/confirm", json={"pending_id": parsed["pending_id"]})
    assert client.get("/api/notes").get_json()["notes"]
    payload = client.get("/api/sales").get_json()
    sales = payload.get("sales")
    if sales is None:
        sales = payload.get("items") or []
    assert sales == []
