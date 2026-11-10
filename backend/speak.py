"""Natural replies from Flask-verified figures only. No SQLite. No invented totals."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("vyaparmitra.speak")


def detect_language(text: str) -> str:
    from intents.language import detect_input_language

    lang = detect_input_language(text)
    return lang if lang in {"en", "hi", "kn", "mr"} else "en"


def _rs(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "0"
    if n == int(n):
        return str(int(n))
    return f"{n:.2f}"


def _tx(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "0"


def _qty(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "0"
    if n == int(n):
        return str(int(n))
    return f"{n:g}"


def sales_reply(lang: str, amount: Any, transactions: Any, *, empty: bool, period: str = "today") -> str:
    rs, n = _rs(amount), _tx(transactions)
    all_time = period == "all"
    if lang == "hi":
        if empty:
            return "अब तक दर्ज बिक्री 0 रुपये है।" if all_time else "आज दुकान की बिक्री 0 रुपये रही। कोई बिल नहीं कटा।"
        if all_time:
            return f"अब तक कुल दर्ज बिक्री {rs} रुपये हुई। {n} बिल कटे।"
        return f"आज कुल बिक्री {rs} रुपये हुई। {n} बिल कटे।"
    if lang == "kn":
        if empty:
            return "ಇಲ್ಲಿಯವರೆಗೆ ಮಾರಾಟ 0 ರೂಪಾಯಿ." if all_time else "ಇಂದು ಮಾರಾಟ 0 ರೂಪಾಯಿ. ಯಾವುದೇ ಬಿಲ್ ಇಲ್ಲ."
        if all_time:
            return f"ಇಲ್ಲಿಯವರೆಗೆ ಒಟ್ಟು ಮಾರಾಟ {rs} ರೂಪಾಯಿ. {n} ಬಿಲ್ ಆಗಿವೆ."
        return f"ಇಂದು ಒಟ್ಟು ಮಾರಾಟ {rs} ರೂಪಾಯಿ. {n} ಬಿಲ್ ಆಗಿವೆ."
    if lang == "mr":
        if empty:
            return "आतापर्यंत विक्री 0 रुपये आहे." if all_time else "आज विक्री 0 रुपये आहे. एकही बिल नाही."
        if all_time:
            return f"आतापर्यंत एकूण विक्री {rs} रुपये झाली. {n} बिले झाली."
        return f"आज एकूण विक्री {rs} रुपये झाली. {n} बिले झाली."
    if empty:
        return "Recorded sales so far are ₹0." if all_time else "Today's recorded sales are ₹0. No bills yet."
    if all_time:
        return f"Recorded sales so far are ₹{rs} in {n} bills."
    return f"Today you sold ₹{rs} in {n} bills."


def _product_phrase(item: dict[str, Any], lang: str) -> str:
    name = item.get("name") or "item"
    qty = _qty(item.get("quantity"))
    unit = item.get("unit") or ""
    amt = _rs(item.get("amount"))
    if lang == "hi":
        return f"{name} {qty} {unit}, {amt} रुपये"
    if lang == "kn":
        return f"{name} {qty} {unit}, {amt} ರೂಪಾಯಿ"
    if lang == "mr":
        return f"{name} {qty} {unit}, {amt} रुपये"
    return f"{name} {qty} {unit}, ₹{amt}"


def _join_products(items: list[dict[str, Any]], lang: str) -> str:
    parts = [_product_phrase(p, lang) for p in items]
    if not parts:
        return ""
    if lang in {"hi", "mr"}:
        return "। ".join(parts)
    if lang == "kn":
        return ". ".join(parts)
    if len(parts) == 1:
        return parts[0]
    return "; ".join(parts)


def _empty_products(lang: str) -> str:
    return {
        "hi": "आज कोई सामान बिका नहीं।",
        "kn": "ಇಂದು ಯಾವುದೇ ವಸ್ತು ಮಾರಾಟವಾಗಿಲ್ಲ.",
        "mr": "आज काहीही विकले नाही.",
        "en": "No products were sold in this period.",
    }[lang]


def _facts_from_result(result: dict[str, Any]) -> dict[str, Any]:
    facts: dict[str, Any] = {"topic": result.get("topic")}
    period = result.get("period") if isinstance(result.get("period"), dict) else None
    if result.get("topic") == "overview":
        today = result.get("today") if isinstance(result.get("today"), dict) else {}
        yest = result.get("yesterday") if isinstance(result.get("yesterday"), dict) else {}
        facts["period_total_amount"] = (period or {}).get("total_amount", result.get("total_amount"))
        facts["period_transactions"] = (period or {}).get("transactions", result.get("transactions"))
        facts["period_from"] = (period or {}).get("from")
        facts["period_to"] = (period or {}).get("to")
        facts["today_total_amount"] = today.get("total_amount")
        facts["today_transactions"] = today.get("transactions")
        facts["yesterday_total_amount"] = yest.get("total_amount")
        facts["yesterday_transactions"] = yest.get("transactions")
        facts["total_amount"] = facts["period_total_amount"]
        facts["transactions"] = facts["period_transactions"]
        facts["scope"] = "period"
    else:
        if period and "total_amount" in period:
            facts["total_amount"] = period.get("total_amount")
        elif "total_amount" in result:
            facts["total_amount"] = result.get("total_amount")
        if period and "transactions" in period:
            facts["transactions"] = period.get("transactions")
        elif "transactions" in result:
            facts["transactions"] = result.get("transactions")
        if period:
            facts["period_from"] = period.get("from")
            facts["period_to"] = period.get("to")
    if result.get("by_product"):
        facts["by_product"] = [
            {
                "name": p.get("name"),
                "quantity": p.get("quantity"),
                "unit": p.get("unit"),
                "amount": p.get("amount"),
            }
            for p in result["by_product"]
        ]
    if result.get("best_selling"):
        b = result["best_selling"]
        facts["best_selling"] = {
            "name": b.get("name"),
            "quantity": b.get("quantity"),
            "unit": b.get("unit"),
            "amount": b.get("amount"),
        }
        facts["metric"] = result.get("metric") or "quantity"
    if result.get("low_stock") is not None:
        facts["low_stock"] = [
            {"name": p.get("name"), "quantity": p.get("current_stock"), "unit": p.get("unit")}
            for p in result["low_stock"]
        ]
    return facts


def _numbers_in(obj: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            found |= _numbers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _numbers_in(v)
    elif isinstance(obj, bool):
        return found
    elif isinstance(obj, (int, float)):
        if float(obj) == int(obj):
            found.add(str(int(obj)))
        else:
            found.add(_rs(obj))
            found.add(_qty(obj))
    return found


def _figures_ok(text: str, facts: dict[str, Any]) -> bool:
    for token in _numbers_in(facts):
        if token not in {"0"} and token not in text.replace(",", ""):
            return False
    for item in facts.get("by_product") or []:
        if item.get("name") and str(item["name"]) not in text:
            return False
    best = facts.get("best_selling") or {}
    if best.get("name") and str(best["name"]) not in text:
        return False
    return True


def _analytics_template(lang: str, result: dict[str, Any]) -> str:
    topic = result.get("topic") or "sales_summary"
    if topic == "overview":
        p = result.get("period") if isinstance(result.get("period"), dict) else {}
        pamt = p.get("total_amount", result.get("total_amount"))
        ptx = p.get("transactions", result.get("transactions"))
        today = result.get("today") if isinstance(result.get("today"), dict) else {}
        yest = result.get("yesterday") if isinstance(result.get("yesterday"), dict) else {}
        today_amt = today.get("total_amount")
        today_tx = today.get("transactions")
        y = yest.get("total_amount")
        pf, pt = p.get("from"), p.get("to")
        return {
            "hi": (
                f"{pf} से {pt} तक दर्ज बिक्री {pamt} रुपये, {ptx} बिल। "
                f"आज अलग से {today_amt} रुपये, {today_tx} बिल; कल {y} रुपये। नकद या मुनाफा नहीं।"
            ),
            "kn": (
                f"{pf} ರಿಂದ {pt} ದಾಖಲೆ ಮಾರಾಟ {pamt} ರೂ, {ptx} ಬಿಲ್. "
                f"ಇಂದು ಪ್ರತ್ಯೇಕವಾಗಿ {today_amt} ರೂ, {today_tx} ಬಿಲ್; ನಿನ್ನೆ {y}. ನಗದು ಅಥವಾ ಲಾಭ ಅಲ್ಲ."
            ),
            "mr": (
                f"{pf} ते {pt} नोंदलेली विक्री {pamt} रुपये, {ptx} बिले. "
                f"आज वेगळे {today_amt} रुपये, {today_tx} बिले; काल {y}. रोकड किंवा नफा नाही."
            ),
            "en": (
                f"This period ({pf} to {pt}): recorded sales ₹{pamt} in {ptx} bills. "
                f"Today separately: ₹{today_amt} in {today_tx} bills; yesterday ₹{y}. Not cash or profit."
            ),
        }[lang]
    if topic == "sales_trend":
        amt = result.get("total_amount")
        rng = result.get("period") or {}
        return {
            "en": f"Recorded sales from {rng.get('from')} to {rng.get('to')} total ₹{amt}. Not cash received.",
            "hi": f"{rng.get('from')} से {rng.get('to')} तक दर्ज बिक्री {amt} रुपये। नकद नहीं।",
            "kn": f"{rng.get('from')} ರಿಂದ {rng.get('to')} ದಾಖಲೆ ಮಾರಾಟ {amt} ರೂ.",
            "mr": f"{rng.get('from')} ते {rng.get('to')} नोंदलेली विक्री {amt} रुपये.",
        }[lang]
    if topic == "period_compare":
        cur = result.get("current") or {}
        prev = result.get("previous") or {}
        pct = result.get("percent_change")
        extra = f" Change {pct}% versus the previous period." if pct is not None else " Previous period had zero recorded sales, so a percentage is not shown."
        return {
            "en": f"Current recorded sales ₹{cur.get('total_amount')} vs previous ₹{prev.get('total_amount')}.{extra} No cause is inferred.",
            "hi": f"इस अवधि की दर्ज बिक्री {cur.get('total_amount')} रुपये, पिछली {prev.get('total_amount')}। कारण नहीं बताया।",
            "kn": f"ಈ ಅವಧಿ {cur.get('total_amount')} ರೂ, ಹಿಂದಿನ {prev.get('total_amount')}. ಕಾರಣ ಊಹಿಸಿಲ್ಲ.",
            "mr": f"सध्या {cur.get('total_amount')} रुपये, मागील {prev.get('total_amount')}. कारण गृहीत धरले नाही.",
        }[lang]
    if topic == "unknown_stock":
        rows = result.get("inventory") or []
        if not rows:
            return {"en": "No products are marked as uncounted stock.", "hi": "बिना गिने स्टॉक वाला सामान नहीं है।", "kn": "ಎಣಿಸದ ಸ್ಟಾಕ್ ಇಲ್ಲ.", "mr": "न मोजलेला स्टॉक नाही."}[lang]
        names = ", ".join(p.get("name") or "" for p in rows[:8])
        return {"en": f"Stock not counted: {names}.", "hi": f"स्टॉक नहीं गिना: {names}।", "kn": f"ಎಣಿಸಿಲ್ಲ: {names}.", "mr": f"स्टॉक मोजलेला नाही: {names}."}[lang]
    if topic == "slow_moving":
        rows = result.get("slow_moving") or []
        if not rows:
            return {"en": "No counted products had zero recorded sales in this period.", "hi": "इस अवधि में शून्य बिक्री वाला गिना सामान नहीं।", "kn": "ಈ ಅವಧಿಯಲ್ಲಿ ಶೂನ್ಯ ಮಾರಾಟದ ಎಣಿಸಿದ ವಸ್ತು ಇಲ್ಲ.", "mr": "या काळात शून्य विक्रीचा मोजलेला माल नाही."}[lang]
        names = ", ".join(p.get("name") or "" for p in rows[:8])
        return {"en": f"Counted items with no recorded sales in this period: {names}. Not a demand forecast.", "hi": f"इस अवधि में दर्ज बिक्री शून्य: {names}।", "kn": f"ಮಾರಾಟ ದಾಖಲೆ ಇಲ್ಲ: {names}.", "mr": f"या काळात विक्री नाही: {names}."}[lang]
    if topic == "unsupported":
        return {
            "hi": "मुनाफा या नकद मिली रकम नहीं बता सकता। केवल दर्ज बिक्री बता सकता हूँ।",
            "kn": "ಲಾಭ ಅಥವಾ ನಗದು ಸಿಕ್ಕ ಮೊತ್ತ ಹೇಳಲು ಆಗುವುದಿಲ್ಲ. ದಾಖಲಾದ ಮಾರಾಟ ಮಾತ್ರ ಹೇಳುತ್ತೇನೆ.",
            "mr": "नफा किंवा मिळालेली रोकड सांगता येणार नाही. फक्त नोंदलेली विक्री सांगतो.",
            "en": "I can only share recorded sales, not profit or cash received.",
        }[lang]
    if topic == "low_stock":
        rows = result.get("low_stock") or []
        if not rows:
            return {
                "hi": "अभी कोई सामान कम स्टॉक में नहीं है।",
                "kn": "ಈಗ ಕಡಿಮೆ ಸ್ಟಾಕ್ ಇರುವ ವಸ್ತು ಇಲ್ಲ.",
                "mr": "आता कमी स्टॉकमध्ये काही नाही.",
                "en": "Nothing is at or below its low-stock level.",
            }[lang]
        names = ", ".join(
            f"{p.get('name')} ({_qty(p.get('current_stock'))} {p.get('unit') or ''})".strip()
            for p in rows
        )
        return {
            "hi": f"कम स्टॉक: {names}।",
            "kn": f"ಕಡಿಮೆ ಸ್ಟಾಕ್: {names}.",
            "mr": f"कमी स्टॉक: {names}.",
            "en": f"Low stock: {names}.",
        }[lang]
    if topic == "best_selling_product":
        best = result.get("best_selling")
        if not best:
            return _empty_products(lang)
        phrase = _product_phrase(best, lang)
        return {
            "hi": f"सबसे ज्यादा बिका (मात्रा के हिसाब से): {phrase}।",
            "kn": f"ಹೆಚ್ಚು ಮಾರಾಟವಾದದ್ದು (ಪ್ರಮಾಣದ ಪ್ರಕಾರ): {phrase}.",
            "mr": f"सर्वात जास्त विकले (प्रमाणानुसार): {phrase}.",
            "en": f"Best seller by quantity sold: {phrase}.",
        }[lang]
    products = result.get("by_product") or []
    if topic == "product_breakdown":
        if not products:
            return _empty_products(lang)
        body = _join_products(products, lang)
        return {
            "hi": f"आज बिका: {body}।",
            "kn": f"ಇಂದು ಮಾರಾಟ: {body}.",
            "mr": f"आज विकले: {body}.",
            "en": f"You sold: {body}.",
        }[lang]
    if topic == "product_sales":
        if not products:
            q = result.get("product_query") or "that item"
            return {
                "hi": f"{q} की बिक्री इस अवधि में नहीं मिली।",
                "kn": f"{q} ಮಾರಾಟ ಈ ಅವಧಿಯಲ್ಲಿ ಇಲ್ಲ.",
                "mr": f"{q} ची विक्री या काळात नाही.",
                "en": f"No recorded sales for {q} in this period.",
            }[lang]
        body = _join_products(products, lang)
        return {
            "hi": f"बिक्री: {body}।",
            "kn": f"ಮಾರಾಟ: {body}.",
            "mr": f"विक्री: {body}.",
            "en": f"Sales: {body}.",
        }[lang]
    amt = result.get("total_amount")
    tx = result.get("transactions")
    empty = float(amt or 0) == 0 and int(tx or 0) == 0
    period = result.get("period") or "today"
    if isinstance(period, dict):
        period = "range"
    summary = sales_reply(lang, amt, tx, empty=empty, period=str(period))
    if topic == "sales_summary_and_products":
        if not products:
            return summary + " " + _empty_products(lang)
        body = _join_products(products, lang)
        extra = {
            "hi": f"सामान: {body}।",
            "kn": f"ವಸ್ತುಗಳು: {body}.",
            "mr": f"सामान: {body}.",
            "en": f"Items: {body}.",
        }[lang]
        return f"{summary} {extra}"
    if topic in {"sales", "sales_summary", None}:
        return summary
    return summary


def _maybe_word(transcript: str, lang: str, template: str, result: dict[str, Any]) -> str:
    try:
        from llm import gemini
    except Exception:
        return template
    from config import Config

    if not gemini.configured() or not (Config.GEMINI_API_KEY or "").strip():
        return template
    facts = _facts_from_result(result)
    try:
        polished = gemini.word_reply(facts, lang, template)
    except Exception:
        logger.warning("Gemini wording raised; using template")
        return template
    if not polished or not _figures_ok(polished, facts):
        return template
    if "?" in polished or "？" in polished:
        return template
    if transcript and polished.strip()[:24] == (transcript or "").strip()[:24]:
        return template
    return polished


def sale_recorded_prompt(lang: str, qty: Any, unit: str, name: str, amount: Any) -> str:
    q, a = _qty(qty), _rs(amount)
    u = unit or ""
    if lang == "hi":
        return f"ठीक है, {q} {u} {name} की बिक्री ₹{a} में दर्ज कर दी गई है।"
    if lang == "kn":
        return f"ಸರಿ, {q} {u} {name} ಮಾರಾಟ ₹{a} ಗೆ ದಾಖಲಾಗಿದೆ."
    if lang == "mr":
        return f"ठीक आहे, {q} {u} {name} ची विक्री ₹{a} मध्ये नोंदली."
    return f"Recorded {q} {u} of {name} for ₹{a}."


def sale_confirm_prompt(lang: str, qty: Any, unit: str, name: str, amount: Any, extra: str = "") -> str:
    q, a = _qty(qty), _rs(amount)
    u = unit or ""
    if lang == "hi":
        return f"{name} {q} {u} की बिक्री {a} रुपये में दर्ज करें?{extra}"
    if lang == "kn":
        return f"{name} {q} {u} ಮಾರಾಟ {a} ರೂಪಾಯಿಗೆ ದಾಖಲಿಸುವುದೇ?{extra}"
    if lang == "mr":
        return f"{name} {q} {u} ची विक्री {a} रुपयांना नोंदवायची?{extra}"
    return f"Record sale of {q} {u} of {name} for {a} INR?{extra}"


def new_product_sale_prompt(lang: str, name: str, qty: Any, unit: str, amount: Any) -> str:
    q, a = _qty(qty), _rs(amount)
    u = unit or ""
    if lang == "hi":
        return (
            f"नया सामान {name}। पुष्टि करें तो बनेगा और {q} {u} की बिक्री {a} रुपये में दर्ज होगी। "
            "स्टॉक अभी अज्ञात रहेगा।"
        )
    if lang == "kn":
        return (
            f"ಹೊಸ ವಸ್ತು {name}. ಖಚಿತಪಡಿಸಿದರೆ ರಚನೆಯಾಗಿ {q} {u} ಮಾರಾಟ {a} ರೂಪಾಯಿಗೆ ದಾಖಲಾಗುತ್ತದೆ. "
            "ಸ್ಟಾಕ್ ಇನ್ನೂ ತಿಳಿದಿಲ್ಲ."
        )
    if lang == "mr":
        return (
            f"नवीन वस्तू {name}. पुष्टी केली तर तयार होईल आणि {q} {u} ची विक्री {a} रुपये नोंदेल. "
            "स्टॉक अज्ञात राहील."
        )
    return (
        f"New product “{name}”. Confirm to create it and record sale of {q} {u} for {a} INR. "
        "Stock stays unknown (not shown as zero)."
    )


def purchase_confirm_prompt(lang: str, qty: Any, unit: str, name: str) -> str:
    q = _qty(qty)
    u = unit or ""
    if lang == "hi":
        return f"{name} {q} {u} स्टॉक में जोड़ें? खरीद कीमत नहीं बताई गई, अनुमान नहीं लगाया जाएगा।"
    if lang == "kn":
        return f"{name} {q} {u} ಸ್ಟಾಕ್‌ಗೆ ಸೇರಿಸುವುದೇ? ಖರೀದಿ ಬೆಲೆ ಹೇಳಿಲ್ಲ, ಊಹಿಸುವುದಿಲ್ಲ."
    if lang == "mr":
        return f"{name} {q} {u} स्टॉकमध्ये जमा करायचे? खरेदी किंमत सांगितली नाही, अंदाज लावला जाणार नाही."
    return f"Add {q} {u} of {name} to stock? Purchase cost was not given and will not be invented."


def pending_wait_prompt(lang: str) -> str:
    return {
        "hi": "पहले हाँ या ना कहें। पुष्टि के बाद ही बिक्री दर्ज होगी।",
        "kn": "ಮೊದಲು ಹೌದು ಅಥವಾ ಬೇಡ ಹೇಳಿ. ಖಚಿತಪಡಿಸಿದ ನಂತರವೇ ಮಾರಾಟ ದಾಖಲಾಗುತ್ತದೆ.",
        "mr": "आधी होय किंवा नाही सांगा. पुष्टीनंतरच विक्री नोंदेल.",
        "en": "Please say yes to record it, or no to cancel. Nothing is saved until you confirm.",
    }.get(lang, "Please say yes to record it, or no to cancel. Nothing is saved until you confirm.")


def from_payload(transcript: str, payload: dict[str, Any]) -> tuple[str, str]:
    from intents.language import resolve_reply_language, stick_reply_language

    mode = payload.get("language_mode") or "auto"
    lang, _det, _c = resolve_reply_language(transcript, mode=str(mode))
    if payload.get("language") in {"en", "hi", "kn", "mr"} and mode == "auto":
        lang = payload["language"]
    if payload.get("reply_language") in {"en", "hi", "kn", "mr"}:
        lang = payload["reply_language"]
    sess = payload.get("session_reply_language")
    if sess in {"en", "hi", "kn", "mr"} and str(mode) == "auto":
        lang, _, _ = stick_reply_language(transcript, mode=str(mode), session_lang=sess)
    intent = payload.get("intent")
    result = payload.get("result") if isinstance(payload.get("result"), dict) else None
    msg = (payload.get("message") or "").strip()

    if intent == "check_analytics" and result:
        topic = result.get("topic")
        if topic in {
            None,
            "sales",
            "sales_summary",
            "product_breakdown",
            "sales_summary_and_products",
            "best_selling_product",
            "best_sellers",
            "product_sales",
            "low_stock",
            "stock",
            "unsupported",
            "overview",
            "sales_trend",
            "period_compare",
            "unknown_stock",
            "slow_moving",
        }:
            if topic == "stock":
                inv = result.get("inventory") or []
                n = len(inv)
                text = {
                    "hi": f"स्टॉक सूची में {n} सामान हैं।",
                    "kn": f"ಸ್ಟಾಕ್ ಪಟ್ಟಿಯಲ್ಲಿ {n} ವಸ್ತುಗಳಿವೆ.",
                    "mr": f"स्टॉक यादीत {n} वस्तू आहेत.",
                    "en": f"Inventory has {n} products.",
                }[lang]
                return text, lang
            template = _analytics_template(lang, result)
            return _maybe_word(transcript, lang, template, result), lang
    if intent == "record_sale" and payload.get("executed") and result:
        sale = result.get("sale") if isinstance(result.get("sale"), dict) else result
        amt = sale.get("total_amount") if isinstance(sale, dict) else None
        if amt is None:
            amt = payload.get("sale_amount")
        name = None
        if isinstance(sale, dict) and sale.get("items"):
            name = (sale["items"][0] or {}).get("product_name")
        name = name or payload.get("product_query") or "item"
        qty = payload.get("quantity")
        unit = payload.get("unit") or ""
        if isinstance(sale, dict) and sale.get("items"):
            item0 = sale["items"][0] or {}
            qty = qty if qty is not None else item0.get("quantity")
            unit = unit or item0.get("unit") or ""
        return sale_recorded_prompt(lang, qty, unit, name, amt), lang
    if intent == "check_stock" and result:
        name = result.get("name") or "that product"
        if result.get("stock_known") is False:
            lines = {
                "hi": f"{name} का स्टॉक अभी गिना नहीं गया है।",
                "kn": f"{name} ಸ್ಟಾಕ್ ಇನ್ನೂ ಎಣಿಸಿಲ್ಲ.",
                "mr": f"{name} चा स्टॉक अद्याप मोजलेला नाही.",
                "en": f"{name}: stock has not been counted yet.",
            }
            return lines.get(lang, lines["en"]), lang
        qty, unit = result.get("quantity"), result.get("unit") or ""
        lines = {
            "hi": f"{name} में {qty} {unit} बचा है।",
            "kn": f"{name} ನಲ್ಲಿ {qty} {unit} ಉಳಿದಿದೆ.",
            "mr": f"{name} मध्ये {qty} {unit} शिल्लक आहे.",
            "en": f"{name}: {qty} {unit} remaining.",
        }
        return lines.get(lang, lines["en"]), lang
    if intent in {
        "general_conversation",
        "general_question",
        "business_advice",
        "confirmation",
        "cancellation",
        "clarification",
        "memory_save",
        "memory_list",
        "memory_forget",
        "memory_skip",
    } and msg:
        return msg, lang
    if payload.get("missing") and payload.get("message") and payload.get("conversation_state") == "clarification":
        return str(payload["message"]), lang
    if payload.get("missing"):
        lines = {
            "hi": "कुछ जानकारी कम है। मात्रा या रकम बोलिए।",
            "kn": "ಕೆಲವು ಮಾಹಿತಿ ಕಡಿಮೆ ಇದೆ. ಪ್ರಮಾಣ ಅಥವಾ ಮೊತ್ತ ಹೇಳಿ.",
            "mr": "काही माहिती कमी आहे. प्रमाण किंवा रक्कम सांगा.",
            "en": "Some information is missing. Please say the quantity or amount.",
        }
        return lines.get(lang, lines["en"]), lang
    if msg:
        return msg, lang
    return "I could not answer from the shop records.", lang


def with_reply(payload: dict[str, Any], transcript: str) -> dict[str, Any]:
    text, lang = from_payload(transcript, payload)
    payload["reply_text"] = text
    payload["reply_language"] = lang
    payload["tts_available"] = True
    return payload
