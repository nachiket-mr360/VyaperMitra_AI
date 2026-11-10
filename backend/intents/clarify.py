"""One-question clarification. Never invents values or confirms mutations."""

from __future__ import annotations

import re
from typing import Any

from intents.parser import NUMBER_RE, _extract_amount, _extract_quantity_unit, _fold_digits, _norm_space
from validate import normalize_text

_Q = {
    "quantity": {
        "en": "How much {product} did you {verb}?",
        "hi": "{product} कितना {verb}?",
        "kn": "{product} ಎಷ್ಟು {verb}?",
        "mr": "{product} किती {verb}?",
    },
    "unit": {
        "en": "Which unit — kg, litre, or pieces?",
        "hi": "इकाई क्या है — किलो, लीटर या नग?",
        "kn": "ಯೂನಿಟ್ ಯಾವುದು — ಕೆಜಿ, ಲೀಟರ್ ಅಥವಾ ಪೀಸ್?",
        "mr": "एकक काय — किलो, लिटर की नग?",
    },
    "sale_amount": {
        "en": "For how many rupees was that sale recorded?",
        "hi": "वह बिक्री कितने रुपये की थी?",
        "kn": "ಆ ಮಾರಾಟ ಎಷ್ಟು ರೂಪಾಯಿ?",
        "mr": "ती विक्री किती रुपयांची होती?",
    },
    "product": {
        "en": "Which product do you mean?",
        "hi": "कौन सा सामान?",
        "kn": "ಯಾವ ವಸ್ತು?",
        "mr": "कोणता माल?",
    },
    "time": {
        "en": "What time should I remind you?",
        "hi": "किस समय याद दिलाऊँ?",
        "kn": "ಯಾವ ಸಮಯಕ್ಕೆ ನೆನಪಿಸಲಿ?",
        "mr": "किती वाजता आठवण करू?",
    },
    "date": {
        "en": "On which day should I remind you?",
        "hi": "किस दिन याद दिलाऊँ?",
        "kn": "ಯಾವ ದಿನ ನೆನಪಿಸಲಿ?",
        "mr": "कोणत्या दिवशी आठवण करू?",
    },
    "title": {
        "en": "What should the reminder say?",
        "hi": "रिमाइंडर में क्या लिखूँ?",
        "kn": "ರಿಮೈಂಡರ್‌ನಲ್ಲಿ ಏನು ಹೇಳಲಿ?",
        "mr": "आठवणीत काय लिहू?",
    },
    "metric": {
        "en": "Do you want to compare products by quantity sold or total recorded sales amount?",
        "hi": "मात्रा से तुलना करूँ या दर्ज बिक्री राशि से?",
        "kn": "ಮಾರಾಟದ ಪ್ರಮಾಣವೋ ಅಥವಾ ದಾಖಲಿತ ಮೊತ್ತವೋ?",
        "mr": "विक्री प्रमाणाने तुलना करू की नोंदलेल्या रकमेने?",
    },
}


def first_missing(missing: list[str]) -> str | None:
    order = ["product", "quantity", "unit", "sale_amount", "date", "time", "title", "metric", "body"]
    for key in order:
        if key in missing:
            return key
    return missing[0] if missing else None


def question(
    missing: list[str],
    *,
    lang: str,
    product: str | None,
    intent: str,
    pending_hour: int | None = None,
) -> str:
    field = first_missing(missing) or "product"
    if field == "time" and pending_hour:
        h = int(pending_hour)
        amp = {
            "en": f"Is {h} o'clock in the morning or in the evening?",
            "hi": f"सुबह {h} बजे या शाम {h} बजे?",
            "kn": f"ಬೆಳಿಗ್ಗೆ {h} ಗಂಟೆಯೋ ಸಂಜೆ {h} ಗಂಟೆಯೋ?",
            "mr": f"सकाळी {h} वाजता की संध्याकाळी {h} वाजता?",
        }
        return amp.get(lang) or amp["en"]
    pack = _Q.get(field) or _Q["product"]
    line = pack.get(lang) or pack["en"]
    verb = "purchase" if intent == "purchase_stock" else "sell"
    if lang == "hi":
        verb = "खरीदा" if intent == "purchase_stock" else "बेचा"
    elif lang == "kn":
        verb = "ಖರೀದಿಸಿದಿರಿ" if intent == "purchase_stock" else "ಮಾರಿದಿರಿ"
    elif lang == "mr":
        verb = "खरेदी केले" if intent == "purchase_stock" else "विकले"
    return line.format(product=product or "it", verb=verb)


def extract_fill(transcript: str) -> dict[str, Any]:
    folded = _norm_space(_fold_digits(transcript or ""))
    out: dict[str, Any] = {}
    qty, unit = _extract_quantity_unit(transcript or "")
    if qty is not None:
        out["quantity"] = qty
    if unit:
        out["unit"] = unit
    amt = _extract_amount(transcript or "")
    if amt is not None:
        out["sale_amount"] = amt
    else:
        nums = NUMBER_RE.findall(_fold_digits(folded))
        if nums and re.search(r"rupee|₹|rs\.?|रूपीज|रुपयों|रुपये|ರೂ", folded, re.I):
            try:
                out["sale_amount"] = float(nums[-1])
            except ValueError:
                pass
    if re.search(r"\bamount\b|total sales|recorded sales|रकम|ಮೊತ್ತ|रक्कम", folded, re.I):
        out["metric"] = "amount"
    if re.search(r"\bquantity\b|units sold|कितने पीस|ಪ್ರಮಾಣ|प्रमाण", folded, re.I):
        out["metric"] = "quantity"
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", folded, re.I)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        ap = (m.group(3) or "").lower()
        if "p" in ap and hh < 12:
            hh += 12
        if "a" in ap and hh == 12:
            hh = 0
        if 0 <= hh <= 23:
            out["time"] = f"{hh:02d}:{mm:02d}"
    if re.search(r"सुबह|morning|\bam\b|ಬೆಳಿಗ್ಗೆ|सकाळी", transcript or "", re.I):
        out["ampm"] = "am"
    if re.search(r"शाम|evening|\bpm\b|ಸಂಜೆ|संध्याकाळी", transcript or "", re.I):
        out["ampm"] = "pm"
    hm = re.search(r"([0-9०-९೦-೯]{1,2})\s*(?:बजे|ಗಂಟೆಗೆ|वाजता)?", folded)
    if hm and (out.get("ampm") or re.search(r"बजे|ಗಂಟೆಗೆ|वाजता", folded)):
        try:
            from intents.ops_parser import _ascii_num

            out["hour"] = _ascii_num(hm.group(1))
        except (ValueError, TypeError):
            pass
    from intents.ops_parser import _word_hour

    wh = _word_hour(transcript or "")
    if wh:
        out["hour"] = wh
    return out


def apply_fill(slot: dict[str, Any], fill: dict[str, Any]) -> dict[str, Any]:
    merged = dict(slot)
    missing = list(merged.get("missing") or [])
    for key, val in fill.items():
        if val is None or val == "":
            continue
        if key == "quantity" and merged.get("quantity") is None:
            merged["quantity"] = val
        elif key == "unit" and not merged.get("unit"):
            merged["unit"] = val
        elif key == "sale_amount" and merged.get("sale_amount") is None:
            merged["sale_amount"] = val
        elif key == "time" and not merged.get("due_time"):
            merged["due_time"] = val
        elif key == "hour" and val:
            merged["pending_hour"] = int(val)
        elif key == "ampm" and val:
            hour = merged.get("pending_hour") or merged.get("hour")
            if hour is not None:
                h = int(hour)
                if val == "pm" and h < 12:
                    h += 12
                if val == "am" and h == 12:
                    h = 0
                merged["due_time"] = f"{h:02d}:00"
        elif key == "metric":
            merged["metric"] = val
        elif key in {"product", "product_query"}:
            merged["product_query"] = val
            if "product" in missing:
                missing = [m for m in missing if m != "product"]
        if key in missing:
            missing = [m for m in missing if m != key]
        if key == "quantity" and "quantity" not in missing and merged.get("unit") and "unit" in missing:
            missing = [m for m in missing if m != "unit"]
        if key == "time" and "time" in missing:
            missing = [m for m in missing if m != "time"]
        if key == "ampm" and merged.get("due_time") and "time" in missing:
            missing = [m for m in missing if m != "time"]
    if merged.get("quantity") is not None and "quantity" in missing:
        missing = [m for m in missing if m != "quantity"]
    if merged.get("unit") and "unit" in missing:
        missing = [m for m in missing if m != "unit"]
    if merged.get("sale_amount") is not None and "sale_amount" in missing:
        missing = [m for m in missing if m != "sale_amount"]
    if merged.get("ampm") and merged.get("pending_hour") is not None:
        h = int(merged["pending_hour"])
        if merged["ampm"] == "pm" and h < 12:
            h += 12
        if merged["ampm"] == "am" and h == 12:
            h = 0
        merged["due_time"] = f"{h:02d}:00"
    if merged.get("due_time") and "time" in missing:
        missing = [m for m in missing if m != "time"]
    merged["missing"] = missing
    return merged


def wants_metric_choice(text: str) -> bool:
    n = normalize_text(text or "")
    if re.search(r"best[- ]?sell|most sold|top sell", n):
        return False
    return bool(re.search(r"performs best|best product|which product is best|सबसे अच्छा उत्पाद", n))
