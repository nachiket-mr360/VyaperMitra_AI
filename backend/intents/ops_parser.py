from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from intents.parser import is_low_stock_list_query
from timeutil import now_business

_REMIND = (
    "remind me to",
    "remind me",
    "set a reminder to",
    "set reminder",
    "reminder to",
    "की याद दिलाना",
    "याद दिलाना",
    "याद दिलाओ",
    "रिमाइंड",
    "ನೆನಪು ಮಾಡು",
    "ನೆನಪಿಡು",
    "ನೆನಪಿಸು",
    "आठवण करून दे",
    "आठवण करून",
    "आठवण कर",
    "आठवण दे",
    "आठवण",
)
_NOTE = (
    "save a note",
    "add a note",
    "make a note",
    "note that",
    "note:",
    "नोट लिखो कि",
    "नोट लिखो",
    "नोट ",
    "टिपण्णी",
    "टिपणी",
    "ನೆನಪಿನ ಟಿಪ್ಪಣಿ",
    "ನೋಟ್ ಮಾಡು",
    "ಟಿಪ್ಪಣಿ",
    "नोंद कर",
    "नोंद",
)
_DIGIT_MAP = str.maketrans(
    "०१२३४५६७८९೦೧೨೩೪೫೬೭೮೯",
    "01234567890123456789",
)
_DELETE_REM = (
    "delete reminder",
    "cancel reminder",
    "remove reminder",
    "रिमाइंडर हटाओ",
    "रिमाइंडर रद्द",
    "ರಿಮೈಂಡರ್ ಅಳಿಸು",
    "ನೆನಪು ಅಳಿಸು",
    "ನೆನಪು ತೆಗೆದುಹಾಕು",
    "आठवण काढून टाक",
    "रिमाइंडर काढून टाक",
    "आठवण काढ",
    "रिमाइंडर काढ",
)
_COMPLETE = ("mark reminder done", "complete reminder", "reminder done", "रिमाइंडर पूरा")
_LIST_REM = (
    "list reminders",
    "show reminders",
    "upcoming reminders",
    "रिमाइंडर दिखाओ",
    "ನೆನಪುಗಳನ್ನು ತೋರಿಸು",
    "ರಿಮೈಂಡರ್ ತೋರಿಸು",
    "ನೆನಪು ತೋರಿಸು",
    "आठवणी दाखवा",
    "रिमाइंडर दाखवा",
)
_LIST_NOTES = (
    "list notes",
    "show notes",
    "नोट दिखाओ",
    "ಟಿಪ್ಪಣಿಗಳನ್ನು ತೋರಿಸು",
    "ನೋಟ್ ತೋರಿಸು",
    "ಟಿಪ್ಪಣಿ ತೋರಿಸು",
    "नोंदी दाखवा",
    "नोट दाखवा",
)
_BRIEF = ("daily briefing", "today briefing", "briefing", "आज का सार", "आजचा सारांश")
_DELETE_NOTE = (
    "delete note",
    "remove note",
    "नोट हटाओ",
    "ಟಿಪ್ಪಣಿ ಅಳಿಸು",
    "ನೋಟ್ ಅಳಿಸು",
    "नोंद काढून टाक",
    "नोट काढून टाक",
    "नोंद काढ",
)

_WEEK = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "सोमवार": 0, "मंगलवार": 1, "बुधवार": 2, "गुरुवार": 3, "शुक्रवार": 4, "शनिवार": 5, "रविवार": 6,
    "ಸೋಮವಾರ": 0, "ಮಂಗಳವಾರ": 1, "ಬುಧವಾರ": 2, "ಗುರುವಾರ": 3, "ಶುಕ್ರವಾರ": 4, "ಶನಿವಾರ": 5, "ಭಾನುವಾರ": 6,
    "सोमवारी": 0, "मंगळवारी": 1, "बुधवारी": 2, "गुरुवारी": 3, "शुक्रवारी": 4, "शनिवारी": 5, "रविवारी": 6,
}

_DATE_STOP = (
    "tomorrow", "today", "tonight", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "every", "daily", "on the", "at ", "am", "pm",
    "कल", "आज", "सोमवार", "मंगलवार", "हर ", "सुबह", "बजे",
    "ನಾಳೆ", "ಇಂದು", "ಸೋಮವಾರ", "ಪ್ರತಿ", "ಬೆಳಿಗ್ಗೆ",
    "उद्या", "सकाळी", "आठवण",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _language(text: str) -> str:
    if re.search(r"[\u0C80-\u0CFF]", text):
        return "kn"
    if re.search(r"[\u0900-\u097F]", text):
        if re.search(r"उद्या|सकाळी|आठवण|किती|झाली|एकूण|आजची|तुमची|विक्री|पदार्थ", text):
            return "mr"
        return "hi"
    return "en"


def _contains(text: str, phrases: tuple[str, ...]) -> str | None:
    low = text.lower()
    for p in phrases:
        if p.lower() in low:
            return p
    return None


def _next_weekday(now: datetime, wd: int) -> datetime:
    delta = (wd - now.weekday()) % 7
    if delta == 0:
        delta = 7
    return (now + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)


def _ascii_num(value: str) -> int:
    return int(value.translate(_DIGIT_MAP))


_HOUR_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9,
    "दस": 10, "ग्यारह": 11, "बारह": 12,
}
_HOUR_ALT = "|".join(sorted((_HOUR_WORDS.keys()), key=len, reverse=True))


def _word_hour(text: str) -> int | None:
    marked = re.search(
        rf"({_HOUR_ALT})\s*(?:बजे|ಗಂಟೆಗೆ|वाजता|o'?clock)",
        text or "",
        re.I,
    )
    if marked:
        token = marked.group(1)
        return _HOUR_WORDS.get(token) or _HOUR_WORDS.get(token.lower())
    return None


def _parse_time(text: str) -> tuple[str | None, int | None]:
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", text, re.I)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2) or 0)
        ap = m.group(3).lower().replace(".", "")
        if ap.startswith("p") and h < 12:
            h += 12
        if ap.startswith("a") and h == 12:
            h = 0
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}", None
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}", None
    m = re.search(
        r"([0-9०-९೦-೯]{1,2})\s*(?:बजे|ಗಂಟೆಗೆ|वाजता|:00)?",
        text,
    )
    m2 = re.search(
        r"(?:at|सुबह|शाम|ಬೆಳಿಗ್ಗೆ|ಸಂಜೆ|सकाळी)\s*([0-9०-९೦-೯]{1,2})",
        text,
        re.I,
    )
    hour_token = None
    word_h = _word_hour(text)
    if m2:
        hour_token = m2.group(1)
    elif m and re.search(r"बजे|ಗಂಟೆಗೆ|वाजता|सुबह|शाम|ಬೆಳಿಗ್ಗೆ|सकाळी", text, re.I):
        hour_token = m.group(1)
    pending_hour = None
    if hour_token is None and word_h and re.search(r"बजे|ಗಂಟೆಗೆ|वाजता|o'clock|at\b", text, re.I):
        hour_token = str(word_h)
    if hour_token is not None:
        h = _ascii_num(hour_token) if not str(hour_token).isdigit() else int(hour_token)
        if word_h and hour_token == str(word_h):
            h = word_h
        if 1 <= h <= 12:
            if re.search(r"शाम|evening|\bpm\b|ಸಂಜೆ|संध्याकाळी", text, re.I):
                if h < 12:
                    h += 12
                return f"{h:02d}:00", None
            if re.search(r"सुबह|morning|\bam\b|ಬೆಳಿಗ್ಗೆ|सकाळी", text, re.I):
                if h == 12:
                    h = 0
                return f"{h:02d}:00", None
            pending_hour = h
            return None, pending_hour
        if 0 <= h <= 23:
            return f"{h:02d}:00", None
    if re.search(r"every morning|हर सुबह|प्रत्येक सकाळी|ಪ್ರತಿ ಬೆಳಿಗ್ಗೆ", text, re.I):
        return "09:00", None
    return None, None


def _parse_schedule(text: str) -> dict[str, Any]:
    now = now_business()
    missing: list[str] = []
    rec = "none"
    weekday = None
    month_day = None
    due_date = None
    low = text.lower()

    if re.search(r"\bevery morning\b|हर सुबह|ಪ್ರತಿ ಬೆಳಿಗ್ಗೆ|दररोज सकाळी|every day|daily|हर दिन|ರೋಜು", text, re.I):
        rec = "daily"
        due_date = now.date().isoformat()
        if now.hour >= 9 and "morning" in low:
            due_date = (now + timedelta(days=1)).date().isoformat()
    if re.search(r"every week|हर हफ्ते|प्रत्येक आठवड्या", text, re.I):
        rec = "weekly"

    if re.search(r"\btomorrow\b|कल\b|ನಾಳೆ|उद्या", text, re.I):
        due_date = (now + timedelta(days=1)).date().isoformat()
    elif re.search(r"\btoday\b|आज\b|ಇಂದು", text, re.I):
        due_date = now.date().isoformat()

    for name, wd in _WEEK.items():
        if re.search(rf"\b{re.escape(name)}\b", text, re.I):
            due_date = _next_weekday(now, wd).date().isoformat()
            weekday = wd
            if rec == "none" and re.search(r"every|हर |ಪ್ರತಿ|प्रत्येक", text, re.I):
                rec = "weekly"
            break

    m = re.search(r"\bon the (\d{1,2})(?:st|nd|rd|th)?\b", text, re.I)
    if not m:
        m = re.search(r"(\d{1,2})\s*(?:तारीख|ನೇ)", text)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            month_day = day
            candidate = now.replace(day=min(day, 28))
            try:
                candidate = now.replace(day=day)
            except ValueError:
                candidate = now.replace(day=min(day, 28))
            if candidate.date() < now.date():
                month = now.month + 1
                year = now.year + (month - 1) // 12
                month = (month - 1) % 12 + 1
                candidate = candidate.replace(year=year, month=month)
            due_date = candidate.date().isoformat()
            if rec == "none" and re.search(r"every month|हर महीने", text, re.I):
                rec = "monthly"

    due_time, pending_hour = _parse_time(text)
    if rec == "daily" and due_time is None and pending_hour is None:
        due_time = "09:00"

    if due_date is None:
        missing.append("date")
    if due_time is None:
        if pending_hour is not None or re.search(r"\bat\b|बजे|ಗಂಟೆಗೆ|वाजता", text, re.I):
            missing.append("time")

    return {
        "due_date": due_date,
        "due_time": due_time,
        "pending_hour": pending_hour,
        "recurrence": rec,
        "weekday": weekday,
        "month_day": month_day,
        "missing": missing,
    }


_SCHED_BITS = [
    r"\btomorrow\b",
    r"\btoday\b",
    r"\btonight\b",
    r"\bevery morning\b",
    r"\bevery day\b",
    r"\bdaily\b",
    r"\bon the \d{1,2}(?:st|nd|rd|th)?\b",
    r"\bon (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?",
    r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b",
    r"कल",
    r"आज",
    r"सुबह",
    r"शाम",
    r"मुझे",
    r"[0-9०-९]{1,2}\s*बजे",
    r"बजे",
    r"ನಾಳೆ",
    r"ಇಂದು",
    r"ಬೆಳಿಗ್ಗೆ",
    r"ನನಗೆ",
    r"[0-9೦-೯]{1,2}\s*ಗಂಟೆಗೆ",
    r"ಗಂಟೆಗೆ",
    r"उद्या",
    r"सकाळी",
    r"मला",
    r"[0-9०-९]{1,2}\s*वाजता",
    r"वाजता",
]


def _clean_phrase(text: str) -> str:
    text = re.sub(r"^(to|के|कि|की|that)\s+", "", text.strip(), flags=re.I)
    text = re.sub(r"\s+(एंदು|ಎಂದು|अशी|की)$", "", text.strip(), flags=re.I)
    return text.strip(" .,;:।!?")


def _strip_schedule(text: str) -> str:
    out = text
    for pat in _SCHED_BITS:
        out = re.sub(pat, " ", out, flags=re.I)
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s+\b(on|at|every|to)\b\s*$", "", out, flags=re.I)
    return _clean_phrase(out)


def _canonical_title(title: str) -> str:
    compact = re.sub(r"\s+", " ", title).strip()
    if re.search(
        r"call(?:\s+the)?\s+supplier|सप्लायर\s*को\s*(?:फोन|कॉल)|सप्लायरला\s*फोन|"
        r"ಸಪ್ಲೈಯರ್.*ಕರೆ|ಸರಬರಾಜುದಾರ.*ಕರೆ",
        compact,
        re.I,
    ):
        return "Call supplier"
    return compact


def _extract_task(text: str, marker: str, *, strip_schedule: bool) -> str:
    idx = text.lower().find(marker.lower())
    after = text[idx + len(marker) :] if idx >= 0 else ""
    before = text[:idx] if idx >= 0 else text
    after = _clean_phrase(after)
    before = _clean_phrase(before)
    if strip_schedule:
        after_use = _strip_schedule(after)
        before_use = _strip_schedule(before)
    else:
        after_use, before_use = after, before
    body = after_use if len(after_use) >= 3 else before_use
    return _canonical_title(body) if strip_schedule else body


def _title_after(text: str, marker: str) -> str:
    return _extract_task(text, marker, strip_schedule=True)


def _analytics_period(text: str) -> str:
    if re.search(r"yesterday|कल की|ನಿನ್ನೆ|कालची", text, re.I):
        return "yesterday"
    if re.search(r"this week|इस हफ्ते|इस सप्ताह|ಈ ವಾರ|या आठवड्या", text, re.I):
        return "week"
    if re.search(r"last 30|last thirty|30 days|पिछले 30", text, re.I):
        return "days_30"
    if re.search(r"this month|last month|इस महीने|पिछले महीने|ಈ ತಿಂಗಳು|ಕಳೆದ ತಿಂಗಳು|या महिन्या|मागच्या", text, re.I):
        return "month"
    if re.search(
        r"so far|till now|until now|all time|all-time|आज तक|अब तक|अबतक|"
        r"ಇಲ್ಲಿಯವರೆಗೆ|ಇಲ್ಲಿಯವರೆಗೂ|आतापर्यंत|आत्तापर्यंत",
        text,
        re.I,
    ):
        return "all"
    if re.search(
        r"\btotal sales\b|टोटल सेल्स|कुल बिक्री|ಒಟ್ಟು ಮಾರಾಟ|एकूण विक्री",
        text,
        re.I,
    ) and not re.search(r"today|आज(?! तक)|ಇಂದು|ಇವತ್ತು", text, re.I):
        return "all"
    return "today"


def _named_product(text: str) -> str | None:
    try:
        from catalog import lexicon_key
    except ImportError:
        lexicon_key = lambda _t: None  # noqa: E731
    skip = {
        "today",
        "yesterday",
        "sales",
        "sell",
        "sold",
        "much",
        "what",
        "which",
        "how",
        "did",
        "were",
        "and",
        "the",
        "products",
        "product",
        "stock",
        "today's",
        "आज",
        "बिक्री",
        "सामान",
        "कितनी",
        "कितना",
        "कितने",
        "किती",
        "हुई",
        "झाली",
        "ಮಾರಾಟ",
    }
    for token in re.findall(r"[\w\u0900-\u097F\u0C80-\u0CFF]+", text):
        if token.lower() in skip or token in skip:
            continue
        if lexicon_key(token):
            return token
    m = re.search(
        r"(?:sales of|sale of)\s+([A-Za-z][A-Za-z\- ]{1,40})",
        text,
        re.I,
    )
    if m:
        return m.group(1).strip()
    return None


def _parse_analytics(text: str) -> dict[str, Any] | None:
    low = text.lower()
    if re.search(
        r"\b(sold|bought|purchase|customer)\b.+\d|\d.+\b(kg|g|l|pcs|rupees)\b",
        text,
        re.I,
    ) and not re.search(r"\b(how much|what did|which products|today'?s sales|check )\b", text, re.I):
        return None
    period = _analytics_period(text)

    if re.search(
        r"compare (this )?week with last week|compare .* last week|this week with last week|"
        r"compare (this )?month with last month",
        text,
        re.I,
    ):
        kind = "month" if re.search(r"month", text, re.I) else "week"
        return {
            "intent": "check_analytics",
            "analytics_topic": "period_compare",
            "period": kind,
            "missing": [],
        }
    if re.search(
        r"sales trend|last seven days|last 7 days|trend for|"
        r"इस महीने की बिक्री कैसी|बिक्री कैसी रही|कैसे रहे सेल्स|"
        r"ಈ ತಿಂಗಳ ಮಾರಾಟ ಹೇಗಿದೆ|ಮಾರಾಟ ಹೇಗಿದೆ",
        text,
        re.I,
    ):
        p = "month" if re.search(r"month|महीने|ತಿಂಗಳ", text, re.I) else ("days_30" if re.search(r"30", text) else "week")
        return {"intent": "check_analytics", "analytics_topic": "sales_trend", "period": p, "missing": []}
    if re.search(
        r"how is my business|how are my sales performing|business doing|"
        r"tell me about my business|my business overview|"
        r"मेरे बिजनेस|मेरे व्यवसाय|ನನ್ನ ವ್ಯಾಪಾರ|ಅಂಗಡಿಯಲ್ಲಿ.{0,40}ವ್ಯಾಪಾರ|माझा व्यवसाय",
        text,
        re.I,
    ):
        return {"intent": "check_analytics", "analytics_topic": "overview", "period": "week", "missing": []}
    if re.search(
        r"tell me about (my )?sales|about (my )?sales|"
        r"सेल्स के बारे|बिक्री के बारे|सेल्स बताओ|बिक्री बताओ|"
        r"ಮಾರಾಟದ ಬಗ್ಗೆ|ನನ್ನ ಮಾರಾಟದ|"
        r"विक्री बद्दल|माझ्या विक्री",
        text,
        re.I,
    ) and not re.search(r"total|टोटल|कुल|ಒಟ್ಟು|एकूण", text, re.I):
        return {"intent": "check_analytics", "analytics_topic": "overview", "period": "week", "missing": []}
    if re.search(r"unknown stock|stock not counted|not been counted|uncounted stock", text, re.I):
        return {"intent": "check_analytics", "analytics_topic": "unknown_stock", "period": None, "missing": []}
    if is_low_stock_list_query(text) or re.search(r"running low|running out", text, re.I):
        return {"intent": "check_analytics", "analytics_topic": "low_stock", "period": None, "missing": []}
    if re.search(r"selling slowly|slow[- ]moving|need restocking|restock", text, re.I):
        if re.search(r"restock|running low|need restocking", text, re.I):
            return {"intent": "check_analytics", "analytics_topic": "low_stock", "period": None, "missing": []}
        return {"intent": "check_analytics", "analytics_topic": "slow_moving", "period": "week", "missing": []}
    if re.search(r"\bprofit\b|cash received|मुनाफा|नफा|ನಫಾ|लाभ", text, re.I):
        return {
            "intent": "check_analytics",
            "analytics_topic": "unsupported",
            "period": None,
            "missing": [],
        }
    if is_low_stock_list_query(text) or re.search(
        r"low[- ]?stock|कम स्टॉक|स्टॉक कम|ಕಡಿಮೆ ಸ್ಟಾಕ್|ಸ್ಟಾಕ್ ಕಡಿಮೆ|कमी स्टॉक|स्टॉक कमी",
        text,
        re.I,
    ):
        return {"intent": "check_analytics", "analytics_topic": "low_stock", "period": None, "missing": []}

    asks_products = bool(
        re.search(
            r"what did i sell|which products|what products|products did|"
            r"कौन-कौन|क्या-क्या|क्या क्या|क्या बिका|कौन से सामान|सामान बिक|"
            r"ಯಾವ ವಸ್ತು|ಯಾವ ಉತ್ಪನ್ನಗಳು ಮಾರಾಟ|ಮಾರಾಟವಾದವು|ಮಾರಾಟವಾಗಿವೆ|"
            r"कोणते पदार्थ|काय काय विकले|क्या बेचा",
            text,
            re.I,
        )
    )
    asks_qty_sold = bool(
        re.search(
            r"कितना बिका|कितनी बिकी|कितने बिके|how much (was )?sold|quantity sold|"
            r"ಎಷ್ಟು ಮಾರಾಟವಾಗಿದೆ|किती विकले",
            text,
            re.I,
        )
    )
    asks_summary = bool(
        re.search(
            r"how much did i sell|today'?s sales|recorded sales|total sales|"
            r"how much total sales|what is my total sales|total sales so far|"
            r"what are my total sales|sales have i made|sales so far|"
            r"टोटल सेल्स|टोटल सेल|कुल बिक्री|कुल सेल्स|"
            r"कितनी बिक्री|बिक्री कितनी|कितनी बिक्री हुई|कितना हुआ|"
            r"ಒಟ್ಟು ಮಾರಾಟ|ಎಷ್ಟು ಮಾರಾಟ|ಮಾರಾಟವಾಯಿತು|ಮಾರಾಟವಾಗಿದೆ|ಮಾರಾಟ ಆಗಿದೆ|"
            r"ಎಷ್ಟು ವ್ಯಾಪಾರ|ವ್ಯಾಪಾರ ಆಯಿತು|ಅಂಗಡಿಯಲ್ಲಿ.{0,40}ವ್ಯಾಪಾರ|"
            r"किती विक्री|एकूण विक्री|"
            r"आज की बिक्री|आज का सेल्स|की सेल|सेल बताओ|आज की सेल|"
            r"ಇಂದಿನ ಮಾರಾಟ|ಇವತ್ತಿನ ಮಾರಾಟ|ಇವತ್ತು|"
            r"आजची विक्री|बता सकते हो.*सेल्स|बता सकते हो.*बिक्री|"
            r"टोटल सेल्स के बारे",
            text,
            re.I,
        )
    )
    asks_best = bool(
        re.search(
            r"best[- ]?sell|most sold|top sell|sells the most|selling the most|most selling|"
            r"सबसे ज्यादा (कौन|बिक)|सबसे ज्यादा कौन सा|"
            r"ಯಾವ ಉತ್ಪನ್ನ ಹೆಚ್ಚು|ಹೆಚ್ಚು ಮಾರಾಟವಾಗಿದೆ|ಹೆಚ್ಚು ಮಾರಾಟ|"
            r"कोणता प्रॉडक्ट|सर्वात जास्त विकला|सर्वाधिक विक्री|सर्वात जास्त",
            text,
            re.I,
        )
    )
    named = _named_product(text)
    product_specific = bool(
        named
        and re.search(r"sell|sold|sales|बिक|बिक्री|ಮಾರಾಟ|विक्री", text, re.I)
        and not asks_products
    )

    if asks_best:
        return {
            "intent": "check_analytics",
            "analytics_topic": "best_selling_product",
            "period": period,
            "missing": [],
        }
    if product_specific:
        return {
            "intent": "check_analytics",
            "analytics_topic": "product_sales",
            "period": period,
            "product": named,
            "missing": [],
        }
    if (asks_summary and asks_products) or (asks_products and asks_qty_sold):
        return {
            "intent": "check_analytics",
            "analytics_topic": "sales_summary_and_products",
            "period": period,
            "missing": [],
        }
    if asks_products:
        return {
            "intent": "check_analytics",
            "analytics_topic": "product_breakdown",
            "period": period,
            "missing": [],
        }
    if asks_summary or re.search(
        r"check today'?s sales|sales this week|sales this month|yesterday'?s sales|"
        r"monthly sales|month'?s sales|show monthly|"
        r"कल की बिक्री|ನಿನ್ನೆಯ ಮಾರಾಟ|कालची विक्री",
        text,
        re.I,
    ):
        if re.search(r"yesterday'?s sales|कल की बिक्री|ನಿನ್ನೆಯ ಮಾರಾಟ|कालची विक्री", text, re.I):
            period = "yesterday"
        elif re.search(r"sales this week|this week'?s sales|इस हफ्ते की बिक्री|ಈ ವಾರದ ಮಾರಾಟ", text, re.I):
            period = "week"
        elif re.search(r"sales this month|this month'?s sales|monthly sales|month'?s sales|show monthly|इस महीने की बिक्री", text, re.I):
            period = "month"
        return {
            "intent": "check_analytics",
            "analytics_topic": "sales_summary",
            "period": period,
            "missing": [],
        }
    if re.search(r"product[- ]wise|by product|उत्पाद अनुसार|ಉತ್ಪನ್ನವಾರು|उत्पादनानुसार", text, re.I):
        return {
            "intent": "check_analytics",
            "analytics_topic": "product_breakdown",
            "period": period,
            "missing": [],
        }
    if re.search(r"\b(current stock|show inventory|all stock|पूरा स्टॉक|ಎಲ್ಲಾ ಸ್ಟಾಕ್|सर्व स्टॉक)\b", low):
        return {"intent": "check_analytics", "analytics_topic": "stock", "period": None, "missing": []}
    if re.search(r"सेल्स|sales|बिक्री|ಮಾರಾಟ|विक्री", text, re.I) and re.search(
        r"बताओ|बता |tell |about|बारे|ಹೇಳಿ|ಬಗ್ಗೆ|क्या |कितना|ಎಷ್ಟು|ಆಗಿದೆ|किती",
        text,
        re.I,
    ):
        topic = "sales_summary" if re.search(r"total|टोटल|कुल|ಒಟ್ಟು|एकूण", text, re.I) else "overview"
        return {"intent": "check_analytics", "analytics_topic": topic, "period": period if topic == "sales_summary" else "week", "missing": []}
    return None


def _parse_sale_lifecycle(text: str) -> dict[str, Any] | None:
    new_sale = bool(
        re.search(r"कस्टमर|ग्राहक|customer|लिया|बेचा|sold|took", text, re.I)
        and re.search(r"किलो|kg|रुपये|rupees|₹", text, re.I)
        and not re.search(r"हटा|रद्द|cancel|कीमत|correct|change", text, re.I)
    )
    if new_sale:
        return None
    m = re.search(
        r"(?:cancel|void)\s+(?:bill|sale|invoice)\s*(?:number|no\.?|#)?\s*(\d+)|"
        r"बिल\s*(?:नंबर|संख्या)?\s*(\d+)\s*(?:रद्द|कैंसल)|"
        r"ಬಿಲ್\s*(\d+)\s*ರದ್ದು",
        text,
        re.I,
    )
    if m:
        num = next(g for g in m.groups() if g)
        return {"intent": "cancel_sale", "sale_id": int(num), "missing": []}
    if re.search(r"नोट|रिमाइंड|reminder|\bnote\b", text, re.I):
        pass
    elif re.search(
        r"remove (that |the previous |the last )?(sale|bill)|undo (that|the sale)|"
        r"cancel (that|the last|the previous) (sale|bill)|no,? remove|"
        r"पिछली बिक्री हटा|वो बिक्री हटा|बिक्री हटा दो|रद्द करो|रद्द कर दो|"
        r"इसे हटा(?:\s*दो)?|ये हटा(?:\s*दो)?|हटा दो|"
        r"मागील विक्री काढ|ते बिल रद्द",
        text,
        re.I,
    ):
        return {"intent": "cancel_sale", "sale_id": None, "missing": []}
    amt = re.search(
        r"(?:change (?:that |the price |it )?(?:from\s+\d+\s+)?(?:to|into)\s*(?:₹|rs\.?)?\s*(\d+(?:\.\d+)?))|"
        r"(?:price (?:is|to)\s*(\d+(?:\.\d+)?))|"
        r"(?:(\d+(?:\.\d+)?)\s*(?:रुपये|रुपया|रुपए|₹)\s*(?:करो|कर दो|करा))|"
        r"(?:₹\s*(\d+(?:\.\d+)?))",
        text,
        re.I,
    )
    qty = re.search(
        r"(?:actually[, ]+|it was |make it |change (?:qty|quantity|it) to\s*)"
        r"(\d+(?:\.\d+)?)\s*(kg|किलो|kilo)?|"
        r"(?:(\d+(?:\.\d+)?)\s*(kg|किलो)\s*(?:था|करो|करा))",
        text,
        re.I,
    )
    if re.search(r"correct (the )?last bill|last bill.*(wrong|correct)|पिछला बिल ठीक|करेक्ट.*बिल", text, re.I) or (
        (amt or qty)
        and re.search(
            r"change|correct|actually|wrong|कीमत|दाम|price|"
            r"नहीं|नाही|ಬದಲಾಯಿಸಿ|ಬದಲಾಯಿಸು|कर दो|करो",
            text,
            re.I,
        )
    ):
        out: dict[str, Any] = {"intent": "correct_sale", "target": "last", "missing": []}
        if amt:
            val = next(g for g in amt.groups() if g)
            out["sale_amount"] = float(val)
        if qty:
            qv = qty.group(1) or qty.group(3)
            if qv:
                out["quantity"] = float(qv)
        if out.get("sale_amount") is None and out.get("quantity") is None:
            out["missing"] = ["correction"]
        return out
    m = re.search(
        r"(?:customer\s+)?returned\s+(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pcs)?\s*(?:of\s+)?([a-zA-Z\u0900-\u097F\u0C80-\u0CFF]+)|"
        r"(\d+(?:\.\d+)?)\s*(kg)?\s*([a-zA-Z\u0900-\u097F]+)\s*(?:वापस|लौटा)",
        text,
        re.I,
    )
    if m and re.search(r"return|returned|वापस|लौटा|ರಿಟರ್ನ", text, re.I):
        qty = m.group(1) or m.group(4)
        unit = m.group(2) or m.group(5) or "kg"
        prod = m.group(3) or m.group(6)
        return {
            "intent": "return_sale",
            "quantity": float(qty),
            "unit": unit,
            "product_query": prod,
            "missing": [],
        }
    if re.search(r"find (my )?last sale|last sale|last bill|पिछला बिल|ಕೊನೆಯ ಬಿಲ್", text, re.I):
        if not re.search(r"correct|cancel|return", text, re.I):
            return {"intent": "show_sale", "target": "last", "missing": []}
    return None


def parse_shop_ops(transcript: str) -> dict[str, Any] | None:
    text = _norm(transcript)
    if not text:
        return None
    lang = _language(text)

    life = _parse_sale_lifecycle(text)
    if life:
        life["language"] = lang
        return life

    analytics = _parse_analytics(text)
    if analytics:
        analytics["language"] = lang
        return analytics

    if _contains(text, _BRIEF):
        return {"intent": "daily_briefing", "language": lang}
    if _contains(text, _LIST_REM):
        return {"intent": "list_reminders", "language": lang}
    if _contains(text, _LIST_NOTES):
        return {"intent": "list_notes", "language": lang}

    marker = _contains(text, _DELETE_REM)
    if marker:
        title = _title_after(text, marker)
        return {"intent": "delete_reminder", "title": title or None, "language": lang, "missing": [] if title else ["title"]}
    marker = _contains(text, _COMPLETE)
    if marker:
        title = _title_after(text, marker)
        return {"intent": "complete_reminder", "title": title or None, "language": lang, "missing": [] if title else ["title"]}
    marker = _contains(text, _DELETE_NOTE)
    if marker:
        title = _title_after(text, marker)
        return {"intent": "delete_note", "title": title or None, "language": lang, "missing": [] if title else ["title"]}

    marker = _contains(text, _REMIND)
    if marker:
        sched = _parse_schedule(text)
        title = _extract_task(text, marker, strip_schedule=True)
        missing = list(sched["missing"])
        if not title:
            missing.append("title")
        msg = ""
        if "date" in missing:
            msg = "When should I remind you? Say a day or date."
        elif "time" in missing:
            msg = "What time should I remind you?"
        return {
            "intent": "create_reminder",
            "title": title or None,
            "language": lang,
            "message": msg,
            **sched,
            "missing": missing,
        }

    marker = _contains(text, _NOTE)
    if marker:
        body = _extract_task(text, marker, strip_schedule=False)
        if not body:
            return {"intent": "create_note", "body": None, "language": lang, "missing": ["body"]}
        return {"intent": "create_note", "body": body, "language": lang, "missing": []}

    return None
