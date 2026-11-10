from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any

from db import atomic_connection
from errors import ApiError
from timeutil import business_tz, now_business, parse_business_date

RECUR = frozenset({"none", "daily", "weekly", "monthly"})
STATUSES = frozenset({"open", "completed", "cancelled"})


def _now() -> str:
    return now_business().isoformat()


def _due_at(due_date: str, due_time: str | None) -> str:
    try:
        parse_business_date(due_date)
    except ValueError as exc:
        raise ApiError("Invalid date", 400, "invalid_value") from exc
    hhmm = due_time or "09:00"
    try:
        dt = datetime.strptime(f"{due_date} {hhmm}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ApiError("Invalid date or time", 400, "invalid_value") from exc
    return dt.replace(tzinfo=business_tz()).isoformat()


def _public_reminder(row) -> dict[str, Any]:
    now = now_business()
    due = datetime.fromisoformat(row["due_at"])
    if due.tzinfo is None:
        due = due.replace(tzinfo=business_tz())
    overdue = row["status"] == "open" and due < now
    return {
        "id": row["id"],
        "title": row["title"],
        "due_date": row["due_date"],
        "due_time": row["due_time"],
        "due_at": row["due_at"],
        "recurrence": row["recurrence"],
        "weekday": row["weekday"],
        "month_day": row["month_day"],
        "status": row["status"],
        "language": row["language"],
        "overdue": overdue,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }


def _public_note(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "body": row["body"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_reminder(
    title: str,
    due_date: str,
    due_time: str | None,
    recurrence: str = "none",
    weekday: int | None = None,
    month_day: int | None = None,
    language: str = "en",
    *,
    conn=None,
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ApiError("Reminder title is required", 400, "missing_field")
    if len(title) > 200:
        raise ApiError("Title is too long", 400, "invalid_value")
    rec = (recurrence or "none").strip().lower().replace("_", "-").replace(" ", "-")
    if rec in {"once", "one-time", "onetime"}:
        rec = "none"
    if rec not in RECUR:
        raise ApiError("Invalid recurrence", 400, "invalid_value")
    due_at = _due_at(due_date, due_time)
    if rec == "monthly":
        if month_day is None:
            month_day = int(due_date.split("-")[2])
        else:
            month_day = int(month_day)
        if month_day < 1 or month_day > 31:
            raise ApiError("Invalid month day", 400, "invalid_value")
    now = _now()

    def _run(c):
        cur = c.execute(
            """
            INSERT INTO reminders (
                title, due_date, due_time, due_at, recurrence, weekday, month_day,
                status, language, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (title, due_date, due_time, due_at, rec, weekday, month_day, language, now, now),
        )
        row = c.execute("SELECT * FROM reminders WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _public_reminder(row)

    if conn is not None:
        return _run(conn)
    with atomic_connection() as c:
        return _run(c)


def list_reminders(*, status: str | None = None) -> list[dict[str, Any]]:
    with atomic_connection(immediate=False) as conn:
        if status:
            if status not in STATUSES:
                raise ApiError("Invalid status", 400, "invalid_value")
            rows = conn.execute(
                "SELECT * FROM reminders WHERE status = ? ORDER BY due_at, id",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reminders ORDER BY due_at, id"
            ).fetchall()
        return [_public_reminder(r) for r in rows]


def get_reminder(reminder_id: int) -> dict[str, Any]:
    with atomic_connection(immediate=False) as conn:
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
    if row is None:
        raise ApiError("Reminder not found", 404, "not_found")
    return _public_reminder(row)


def update_reminder(reminder_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    current = get_reminder(reminder_id)
    title = fields.get("title", current["title"])
    due_date = fields.get("due_date", current["due_date"])
    due_time = fields["due_time"] if "due_time" in fields else current["due_time"]
    rec = fields.get("recurrence", current["recurrence"])
    rec = str(rec or "none").strip().lower().replace("_", "-").replace(" ", "-")
    if rec in {"once", "one-time", "onetime"}:
        rec = "none"
    weekday = fields["weekday"] if "weekday" in fields else current["weekday"]
    month_day = fields["month_day"] if "month_day" in fields else current["month_day"]
    if rec not in RECUR:
        raise ApiError("Invalid recurrence", 400, "invalid_value")
    if rec == "monthly" and month_day is None:
        month_day = int(str(due_date).split("-")[2])
    due_at = _due_at(due_date, due_time)
    now = _now()
    with atomic_connection() as conn:
        conn.execute(
            """
            UPDATE reminders SET title=?, due_date=?, due_time=?, due_at=?,
                recurrence=?, weekday=?, month_day=?, updated_at=?
            WHERE id=?
            """,
            (str(title).strip(), due_date, due_time, due_at, rec, weekday, month_day, now, reminder_id),
        )
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return _public_reminder(row)


def _add_calendar_months(due: datetime, months: int, intended_day: int) -> datetime:
    month0 = due.month - 1 + months
    year = due.year + month0 // 12
    month = month0 % 12 + 1
    day = min(intended_day, monthrange(year, month)[1])
    return due.replace(year=year, month=month, day=day)


def _advance(row) -> tuple[str, str | None, str]:
    rec = row["recurrence"]
    due = datetime.fromisoformat(row["due_at"])
    if due.tzinfo is None:
        due = due.replace(tzinfo=business_tz())
    if rec == "daily":
        nxt = due + timedelta(days=1)
    elif rec == "weekly":
        nxt = due + timedelta(days=7)
    elif rec == "monthly":
        intended = row["month_day"] if row["month_day"] is not None else due.day
        nxt = _add_calendar_months(due, 1, int(intended))
    else:
        return row["due_date"], row["due_time"], row["due_at"]
    return nxt.date().isoformat(), nxt.strftime("%H:%M") if row["due_time"] else None, nxt.isoformat()


def complete_reminder(reminder_id: int, *, conn=None) -> dict[str, Any]:
    def _run(c):
        row = c.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        if row is None:
            raise ApiError("Reminder not found", 404, "not_found")
        now = _now()
        if row["recurrence"] and row["recurrence"] != "none":
            d, t, at = _advance(row)
            c.execute(
                """
                UPDATE reminders SET due_date=?, due_time=?, due_at=?, status='open',
                    completed_at=NULL, updated_at=?
                WHERE id=?
                """,
                (d, t, at, now, reminder_id),
            )
        else:
            c.execute(
                "UPDATE reminders SET status='completed', completed_at=?, updated_at=? WHERE id=?",
                (now, now, reminder_id),
            )
        out = c.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return _public_reminder(out)

    if conn is not None:
        return _run(conn)
    with atomic_connection() as c:
        return _run(c)


def delete_reminder(reminder_id: int, *, conn=None) -> dict[str, Any]:
    def _run(c):
        row = c.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        if row is None:
            raise ApiError("Reminder not found", 404, "not_found")
        pub = _public_reminder(row)
        c.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        return pub

    if conn is not None:
        return _run(conn)
    with atomic_connection() as c:
        return _run(c)


def find_open_by_title(query: str) -> list[dict[str, Any]]:
    q = (query or "").strip().lower()
    if not q:
        return []
    with atomic_connection(immediate=False) as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE status = 'open' ORDER BY due_at"
        ).fetchall()
    hits = []
    for row in rows:
        title = str(row["title"]).lower()
        if q in title or title in q:
            hits.append(_public_reminder(row))
    return hits


def briefing() -> dict[str, Any]:
    today = now_business().date().isoformat()
    items = list_reminders()
    notes = list_notes()
    today_items = [r for r in items if r["status"] == "open" and r["due_date"] == today]
    overdue = [r for r in items if r["overdue"]]
    upcoming_all = [
        r
        for r in items
        if r["status"] == "open" and r["due_date"] > today
    ]
    upcoming_limit = 8
    return {
        "timezone": "Asia/Kolkata",
        "date": today,
        "today": today_items,
        "overdue": overdue,
        "upcoming": upcoming_all[:upcoming_limit],
        "upcoming_total": len(upcoming_all),
        "upcoming_limit": upcoming_limit,
        "notes": notes[:10],
        "notify_note": "Alerts show only while this app is open. There is no background push.",
    }


def create_note(body: str, *, conn=None) -> dict[str, Any]:
    body = (body or "").strip()
    if not body:
        raise ApiError("Note text is required", 400, "missing_field")
    if len(body) > 2000:
        raise ApiError("Note is too long", 400, "invalid_value")
    now = _now()

    def _run(c):
        cur = c.execute(
            "INSERT INTO shop_notes (body, created_at, updated_at) VALUES (?, ?, ?)",
            (body, now, now),
        )
        row = c.execute("SELECT * FROM shop_notes WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _public_note(row)

    if conn is not None:
        return _run(conn)
    with atomic_connection() as c:
        return _run(c)


def list_notes(*, query: str | None = None) -> list[dict[str, Any]]:
    with atomic_connection(immediate=False) as conn:
        rows = conn.execute(
            "SELECT * FROM shop_notes ORDER BY datetime(created_at) DESC, id DESC"
        ).fetchall()
        notes = [_public_note(r) for r in rows]
    needle = (query or "").strip().casefold()
    if not needle:
        return notes
    return [n for n in notes if needle in str(n["body"]).casefold()]


def update_note(note_id: int, body: str) -> dict[str, Any]:
    body = (body or "").strip()
    if not body:
        raise ApiError("Note text is required", 400, "missing_field")
    with atomic_connection() as conn:
        row = conn.execute("SELECT * FROM shop_notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise ApiError("Note not found", 404, "not_found")
        conn.execute(
            "UPDATE shop_notes SET body=?, updated_at=? WHERE id=?",
            (body, _now(), note_id),
        )
        out = conn.execute("SELECT * FROM shop_notes WHERE id = ?", (note_id,)).fetchone()
        return _public_note(out)


def delete_note(note_id: int, *, conn=None) -> dict[str, Any]:
    def _run(c):
        row = c.execute("SELECT * FROM shop_notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise ApiError("Note not found", 404, "not_found")
        pub = _public_note(row)
        c.execute("DELETE FROM shop_notes WHERE id = ?", (note_id,))
        return pub

    if conn is not None:
        return _run(conn)
    with atomic_connection() as c:
        return _run(c)
