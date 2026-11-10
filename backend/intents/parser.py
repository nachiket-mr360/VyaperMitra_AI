"""Transparent rule parser. Not an LLM. Prisma only supplies the transcript text."""

from __future__ import annotations

import re

from intents.schemas import ParseDraft
from validate import ALLOWED_UNITS, normalize_text

_DIGIT_MAP = str.maketrans(
    "०१२३४५६७८९૦૧૨૩૪૫૬૭૮૯೦೧೨೩೪೫೬೭೮೯୦୧୨୩୪୫୬୭୮୯௦௧௨௩௪௫௬௭௮௯౦౧౨౩౪౫౬౭౮౯",
    "012345678901234567890123456789012345678901234567890123456789",
)

UNIT_ALIASES = {
    "kg": "kg",
    "kgs": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "किलो": "kg",
    "किलोग्राम": "kg",
    "ಕೆಜಿ": "kg",
    "ಕಿಲೋ": "kg",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "ग्राम": "g",
    "l": "l",
    "lt": "l",
    "liter": "l",
    "litre": "l",
    "liters": "l",
    "litres": "l",
    "लीटर": "l",
    "ಲೀಟರ್": "l",
    "ml": "ml",
    "pcs": "pcs",
    "pc": "pc",
    "piece": "piece",
    "pieces": "pieces",
    "packet": "packet",
    "packets": "pkts",
    "pkt": "pkts",
    "pkts": "pkts",
    "dozen": "dozen",
    "bag": "bag",
    "box": "box",
    "bunch": "bunch",
}

CHECK_MARKERS = (
    "how much",
    "how many",
    "remaining",
    "left in stock",
    "stock of",
    "inventory of",
    "कितना",
    "कितनी",
    "कितने",
    "बचा",
    "बची",
    "स्टॉक",
    "स्टाक",
    "ಎಷ್ಟು",
    "ಉಳಿದ",
    "ಸ್ಟಾಕ್",
    "eshtu",
    "ulida",
    "किती",
    "शिल्लक",
    "उरले",
    "उरलं",
)

STOCK_ONLY_MARKERS = (
    "remaining",
    "left in stock",
    "in stock",
    "stock of",
    "inventory of",
    "current stock",
    "बचा",
    "बची",
    "स्टॉक",
    "स्टाक",
    "ಉಳಿದ",
    "ಸ್ಟಾಕ್",
    "शिल्लक",
    "उरले",
    "उरलं",
)

SALES_QUESTION_MARKERS = (
    "sales",
    "sold",
    "sell",
    "बिक्री",
    "सेल्स",
    "मಾರಾಟ",
    "विक्री",
    "बेचा",
    "टोटल",
    "total",
    "कुल",
    "ಒಟ್ಟು",
    "एकूण",
)

CUSTOMER_MARKERS = (
    "customer",
    "customers",
    "ग्राहकाने",
    "ग्राहक",
    "गाहक",
    "कस्टमर",
    "ಕಸ್ಟಮರ್",
    "ಗ್ರಾಹಕ",
    "ಗಿರಾಕಿ",
)

FIRST_PERSON = (
    "i ",
    "i'",
    "we ",
    "मैंने",
    "मैने",
    "मैं ",
    "हमने",
    "ನಾನು",
    "ನಾವು",
    "मी ",
    "आम्ही",
)

SHOP_MARKERS = (
    "for my shop",
    "for the shop",
    "into stock",
    "restock",
    "दुकान के लिए",
    "दुकान साठी",
    "दुकानासाठी",
    "अंगाडी",
    "ಅಂಗಡಿಗೆ",
    "ಅಂಗಡಿಯ",
    "shop",
    "दुकान",
    "अंगाडी",
    "ದುಕಾನ",
)

SALE_VERBS = (
    "sold",
    "sell",
    "selling",
    "sale of",
    "बेचा",
    "बेची",
    "बेचे",
    "बेच दिया",
    "बेच",
    "बिक्री",
    "ಮಾರಿದೆ",
    "ಮಾರಿದ",
    "ಮಾರಾಟ",
    "maride",
    "विकले",
    "विकलं",
    "विक्री",
    "विकली",
)

CUSTOMER_TAKE_VERBS = (
    "bought",
    "buy",
    "purchased",
    "took",
    "taken",
    "take",
    "लिया",
    "लिये",
    "ली",
    "ले गया",
    "ले गई",
    "खरीदा",
    "खरीदी",
    "ತೆಗೆದುಕೊಂಡ",
    "ತೆಗೆದುಕೊಂಡೆ",
    "ಖರೀದಿಸಿದ",
    "घेतले",
    "घेतलं",
    "घेतला",
    "खरेदी",
)

PURCHASE_VERBS = (
    "purchased",
    "bought",
    "purchase",
    "restock",
    "stocked",
    "खरीदा",
    "खरीदी",
    "खरीदे",
    "खरीद",
    "ಖರೀದಿ",
    "ಖರೀದಿಸಿದೆ",
    "ಖರೀದಿಸಿದ",
    "kharidi",
    "खरेदी",
)

CURRENCY_RE = re.compile(
    r"(?:₹|rs\.?|inr|rupees?|rupee|रूपीज|रूपये|रुपयों|रुपये|रुपया|रुपए|"
    r"ರೂಪಾಯಿಗೆ|ರೂ(?:ಪಾಯಿ)?|रुपयां(?:ना)?)",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")

_STRIP_WORDS = {
    "i",
    "we",
    "of",
    "the",
    "a",
    "an",
    "for",
    "to",
    "and",
    "please",
    "today",
    "आज",
    "just",
    "have",
    "has",
    "had",
    "did",
    "was",
    "is",
    "in",
    "my",
    "me",
    "from",
    "what",
    "about",
    "which",
    "किन",
    "कौन",
    "कौनसे",
    "सामानों",
    "सामान",
    "प्रोडक्ट",
    "ಯಾವ",
    "ವಸ್ತುಗಳು",
    "ವಸ್ತುಗಳ",
    "ವಸ್ತು",
    "कोणत्या",
    "वस्तूंचा",
    "वस्तू",
    "with",
    "into",
    "shop",
    "customer",
    "customers",
    "bought",
    "buy",
    "purchased",
    "purchase",
    "sold",
    "sell",
    "took",
    "taken",
    "take",
    "rupees",
    "rupee",
    "ರೂ",
    "rs",
    "inr",
    "मैंने",
    "मैने",
    "मैं",
    "हमने",
    "का",
    "की",
    "के",
    "है",
    "को",
    "ने",
    "एक",
    "लिए",
    "में",
    "दुकान",
    "ग्राहक",
    "गाहक",
    "कस्टमर",
    "लिया",
    "लिये",
    "ली",
    "खरीदा",
    "खरीदी",
    "बेचा",
    "बेची",
    "ನಾನು",
    "ನಾವು",
    "ಆಫ್",
    "ಒಬ್ಬ",
    "ಗ್ರಾಹಕ",
    "ಗಿರಾಕಿ",
    "ಕಸ್ಟಮರ್",
    "ಅಂಗಡಿಗೆ",
    "ಅಂಗಡಿ",
    "ತೆಗೆದುಕೊಂಡ",
    "ತೆಗೆದುಕೊಂಡೆ",
    "ಖರೀದಿಸಿದೆ",
    "ಖರೀದಿ",
    "ಮಾರಿದೆ",
    "ಮಾರಿದ",
    "ರೂಪಾಯಿ",
    "ರೂಪಾಯಿಗೆ",
    "ರೂ",
    "मी",
    "आम्ही",
    "च्या",
    "एका",
    "ग्राहकाने",
    "ग्राहक",
    "दुकानासाठी",
    "दुकानसाठी",
    "घेतले",
    "घेतलं",
    "खरेदी",
    "केली",
    "विकले",
    "रुपये",
    "रुपए",
    "रुपया",
    "रुपयांना",
    "आने",
    "केले",
    "केली",
    "ಗೆ",
    "ರೂಪಾಯಿಗೆ",
    "ರೂಪಾಯಿ",
    "ंना",
    "ना",
}


_WORD_NUMBERS = (
    ("ग्यारह", "11"),
    ("बारह", "12"),
    ("तेरह", "13"),
    ("चौदह", "14"),
    ("पंद्रह", "15"),
    ("सोलह", "16"),
    ("सत्रह", "17"),
    ("अठारह", "18"),
    ("उन्नीस", "19"),
    ("पच्चीस", "25"),
    ("नब्बे", "90"),
    ("अस्सी", "80"),
    ("सत्तर", "70"),
    ("साठ", "60"),
    ("पचास", "50"),
    ("चालीस", "40"),
    ("तीस", "30"),
    ("बीस", "20"),
    ("पाँच", "5"),
    ("पांच", "5"),
    ("दस", "10"),
    ("नौ", "9"),
    ("आठ", "8"),
    ("सात", "7"),
    ("छह", "6"),
    ("चार", "4"),
    ("तीन", "3"),
    ("दो", "2"),
    ("एक", "1"),
    ("ninety", "90"),
    ("eighty", "80"),
    ("seventy", "70"),
    ("sixty", "60"),
    ("fifty", "50"),
    ("forty", "40"),
    ("thirty", "30"),
    ("twenty", "20"),
    ("twelve", "12"),
    ("eleven", "11"),
    ("ten", "10"),
    ("nine", "9"),
    ("eight", "8"),
    ("seven", "7"),
    ("six", "6"),
    ("five", "5"),
    ("four", "4"),
    ("three", "3"),
    ("two", "2"),
    ("one", "1"),
    ("एटी", "80"),
)


def _fold_digits(text: str) -> str:
    return text.translate(_DIGIT_MAP)


_NUM_WORD_FOLLOW = (
    r"(?:kg|g|l|ml|pcs?|pieces?|kilos?|kilograms?|"
    r"किलो|किलोग्राम|ग्राम|लीटर|लिटर|नग|"
    r"₹|rs\.?|inr|rupees?|rupee|रूपीज|रूपये|रुपयों|रुपये|रुपया|रुपए|ರೂ|ರೂಪಾಯಿ|"
    r"सौ|hundred)"
)


def _fold_number_words(text: str) -> str:
    out = text
    for word, digits in sorted(_WORD_NUMBERS, key=lambda p: len(p[0]), reverse=True):
        if word.isascii():
            out = re.sub(rf"(?i)\b{re.escape(word)}\b(?=\s*{_NUM_WORD_FOLLOW}|\s|$)", digits, out)
        else:
            out = re.sub(rf"{re.escape(word)}(?=\s*{_NUM_WORD_FOLLOW}|\s|$)", digits, out)
    out = re.sub(
        r"(\d+)\s*(?:सौ|hundred)\s*(\d+)",
        lambda m: str(int(m.group(1)) * 100 + int(m.group(2))),
        out,
        flags=re.I,
    )
    out = re.sub(
        r"(\d+)\s*(?:सौ|hundred)(?=\s|$)",
        lambda m: str(int(m.group(1)) * 100),
        out,
        flags=re.I,
    )
    out = re.sub(rf"(?<!\d)सौ(?=\s*{_NUM_WORD_FOLLOW})", "100", out)
    out = re.sub(rf"(?i)(?<!\d)\bhundred\b(?=\s*{_NUM_WORD_FOLLOW})", "100", out)
    return out


def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("।", " ").replace(",", " ")).strip()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lower = " " + text.lower() + " "
    return any(m.lower() in lower or m.lower() in text.lower() for m in markers)


_LEFTOVER_STOCK_RE = re.compile(
    r"left(?:\s+in\s+stock)?|remaining|how much .{0,24}(?:left|stock)|"
    r"बचा|बची|बचे|ಉಳಿದ|शिल्लक|उरले|उरलं",
    re.I,
)
_WHICH_ITEMS_RE = re.compile(
    r"(?:which|what)\s+(?:products?|items?)|"
    r"किन(?:\s+दो)?\s+सामान|"
    r"कौन\s*से\s+(?:सामान|प्रोडक्ट)|"
    r"ಯಾವ\s+ವಸ್ತು|"
    r"कोणत्या\s+वस्त",
    re.I,
)
_LOW_STOCK_LIST_RE = re.compile(
    r"low[- ]?stock|running\s+low|running\s+out|"
    r"कम\s*स्टॉक|स्टॉक\s*कम|"
    r"ಕಡಿಮೆ\s*ಸ್ಟಾಕ್|ಸ್ಟಾಕ್\s*ಕಡಿಮೆ|"
    r"कमी\s*स्टॉक|स्टॉक\s*कमी|"
    r"(?:which|what)\s+(?:products?|items?).{0,48}(?:low|running)|"
    r"(?:किन|कौन\s*से|कौनसे).{0,48}(?:स्टॉक\s*कम|कम\s*(?:है|हैं|हैं\?)|प्रोडक्ट\s*कम|कम\s*हैं)|"
    r"ಯಾವ\s+.{0,48}(?:ಸ್ಟಾಕ್\s*ಕಡಿಮೆ|ಕಡಿಮೆ\s*(?:ಇದೆ|ಇವೆ))|"
    r"कोणत्या\s+.{0,48}(?:स्टॉक\s*कमी|कमी\s*(?:आहे|आहेत))",
    re.I,
)


def is_low_stock_list_query(text: str) -> bool:
    """True for inventory *list* questions, not a named product remaining-qty check."""
    raw = (text or "").strip()
    if not raw:
        return False
    leftover = bool(_LEFTOVER_STOCK_RE.search(raw))
    which_items = bool(_WHICH_ITEMS_RE.search(raw))
    if leftover and not which_items:
        return False
    return bool(_LOW_STOCK_LIST_RE.search(raw))


def _classify(text: str) -> str:
    folded = _norm_space(_fold_digits(text))
    if is_low_stock_list_query(text) or is_low_stock_list_query(folded):
        return "unknown"
    sales_q = _contains_any(folded, SALES_QUESTION_MARKERS)
    leftover = bool(_LEFTOVER_STOCK_RE.search(folded) or _LEFTOVER_STOCK_RE.search(text))
    stock_q = _contains_any(folded, STOCK_ONLY_MARKERS) or bool(
        re.search(r"(?<![a-z])stock(?![a-z])", folded, re.I)
        and not re.search(r"restock|stocked", folded, re.I)
    )
    if leftover and not sales_q and (_contains_any(folded, CHECK_MARKERS) or stock_q):
        return "check_stock"
    if stock_q and not sales_q:
        return "check_stock"
    if _contains_any(folded, CHECK_MARKERS) and stock_q:
        return "check_stock"

    customer = _contains_any(folded, CUSTOMER_MARKERS)
    first = _contains_any(folded, FIRST_PERSON)
    shop = _contains_any(folded, SHOP_MARKERS)
    sale_verb = _contains_any(folded, SALE_VERBS)
    take_verb = _contains_any(folded, CUSTOMER_TAKE_VERBS)
    purchase_verb = _contains_any(folded, PURCHASE_VERBS)

    if customer and sale_verb:
        return "record_sale"
    if customer and take_verb:
        return "record_sale"
    if sale_verb and not customer:
        return "record_sale"
    if customer and purchase_verb:
        return "record_sale"
    if customer and not sale_verb and not take_verb and not purchase_verb:
        return "unknown"
    if purchase_verb and not customer and (first or shop):
        return "purchase_stock"
    if purchase_verb and not customer and not first and not shop:
        return "unknown"
    if take_verb and customer:
        return "record_sale"
    if take_verb and first and not customer:
        return "purchase_stock"
    if take_verb and not customer:
        return "unknown"
    return "unknown"


def _extract_amount(text: str) -> float | None:
    folded = _fold_number_words(_fold_digits(text))
    hits: list[float] = []
    for match in CURRENCY_RE.finditer(folded):
        before = folded[max(0, match.start() - 24) : match.start()]
        after = folded[match.end() : match.end() + 16]
        pre = re.search(r"(-?\d+(?:\.\d+)?)\s*$", before)
        post = re.match(r"\s*(-?\d+(?:\.\d+)?)", after)
        if pre:
            hits.append(float(pre.group(1)))
        elif post:
            hits.append(float(post.group(1)))
    if hits:
        return hits[-1]
    rupee_num = re.search(
        r"(-?\d+(?:\.\d+)?)\s*(?:₹|rs\.?|inr|rupees?|रुपये|रुपया|रुपए|ರೂ|रुपयां)",
        folded,
        re.I,
    )
    if rupee_num:
        return float(rupee_num.group(1))
    rupee_num = re.search(
        r"(?:₹|rs\.?|rupees?)\s*(-?\d+(?:\.\d+)?)",
        folded,
        re.I,
    )
    if rupee_num:
        return float(rupee_num.group(1))
    return None


def _extract_quantity_unit(text: str) -> tuple[float | None, str | None]:
    folded = _fold_number_words(_fold_digits(text))
    unit_keys = sorted(UNIT_ALIASES.keys(), key=len, reverse=True)
    pattern = r"(-?\d+(?:\.\d+)?)\s*(" + "|".join(re.escape(u) for u in unit_keys) + r")(?=$|[^\w])"
    match = re.search(pattern, folded, re.I)
    if match:
        qty = float(match.group(1))
        raw_unit = match.group(2)
        unit = UNIT_ALIASES.get(raw_unit.lower()) or UNIT_ALIASES.get(raw_unit)
        if unit is None:
            for alias, canon in UNIT_ALIASES.items():
                if alias.lower() == raw_unit.lower() or alias == raw_unit:
                    unit = canon
                    break
        return qty, unit
    nums = NUMBER_RE.findall(folded)
    amount = _extract_amount(text)
    qty = None
    if nums:
        candidates = [float(n) for n in nums]
        if amount is not None:
            candidates = [c for c in candidates if abs(c - amount) > 1e-9]
        if candidates:
            qty = candidates[0]
    unit = None
    tokens = re.findall(r"[\w\u0900-\u0d7f]+", folded.lower())
    for tok in tokens:
        if tok in UNIT_ALIASES:
            unit = UNIT_ALIASES[tok]
            break
        for alias, canon in UNIT_ALIASES.items():
            if alias.lower() == tok:
                unit = canon
                break
        if unit:
            break
    return qty, unit


_EN_EDGE_CONNECTORS = frozenset(
    {"at", "for", "of", "is", "was", "the", "a", "an", "to", "and"}
)

_PRICE_PREP_RE = re.compile(
    r"(?i)\b(?:at|for)\s*(?:₹|rs\.?|inr)?\s*(?=\d)"
)


def _wipe_phrase(cleaned: str, phrase: str) -> str:
    phrase = phrase.strip()
    if len(phrase) < 3:
        return cleaned
    return re.sub(re.escape(phrase), " ", cleaned, flags=re.I)


def _product_query(text: str) -> str | None:
    folded = _norm_space(_fold_digits(text))
    cleaned = _PRICE_PREP_RE.sub(" ", folded)
    cleaned = CURRENCY_RE.sub(" ", cleaned)
    for extra in (
        "रुपयांना",
        "रुपये",
        "रुपए",
        "रुपया",
        "rupees",
        "rupee",
        "ರೂಪಾಯಿಗೆ",
        "ರೂಪಾಯಿ",
        "ರೂ",
        "रुपये",
        "रुपए",
    ):
        cleaned = re.sub(re.escape(extra), " ", cleaned, flags=re.I)
    cleaned = NUMBER_RE.sub(" ", cleaned)
    phrases: list[str] = []
    for group in (
        CHECK_MARKERS,
        CUSTOMER_MARKERS,
        SALE_VERBS,
        CUSTOMER_TAKE_VERBS,
        PURCHASE_VERBS,
        SHOP_MARKERS,
    ):
        phrases.extend(group)
    for phrase in sorted(phrases, key=len, reverse=True):
        cleaned = _wipe_phrase(cleaned, phrase)
    for alias in sorted(UNIT_ALIASES, key=len, reverse=True):
        if len(alias) <= 2:
            cleaned = re.sub(rf"(?i)\b{re.escape(alias)}\b", " ", cleaned)
        else:
            cleaned = re.sub(re.escape(alias), " ", cleaned, flags=re.I)
    tokens = [
        t
        for t in re.findall(r"[\w\u0900-\u0d7f]+", cleaned.lower())
        if t not in _STRIP_WORDS and len(t) > 1
    ]
    while tokens and tokens[0] in _EN_EDGE_CONNECTORS:
        tokens.pop(0)
    while tokens and tokens[-1] in _EN_EDGE_CONNECTORS:
        tokens.pop()
    if not tokens:
        return None
    if len(tokens) >= 6:
        return None
    joined = normalize_text(" ".join(tokens))
    if re.search(r"बता सकते|टोटल|सेल्स|मಾರಾಟ ಎಷ್ಟು|कुल बिक्री", joined, re.I):
        return None
    return joined


def parse_transcript(transcript: str) -> ParseDraft:
    raw = (transcript or "").strip()
    if not raw:
        return ParseDraft(
            intent="unknown",
            product_query=None,
            quantity=None,
            unit=None,
            sale_amount=None,
            missing=["transcript"],
            error_code="empty_transcript",
            message="No speech text was provided.",
        )

    intent = _classify(raw)
    folded_words = _fold_number_words(_fold_digits(raw))
    amount = _extract_amount(folded_words)
    quantity, unit = _extract_quantity_unit(folded_words)
    product_query = _product_query(folded_words)

    missing: list[str] = []
    error_code = None
    message = ""

    if intent == "unknown":
        return ParseDraft(
            intent="unknown",
            product_query=product_query,
            quantity=quantity,
            unit=unit,
            sale_amount=amount,
            error_code="unsupported_intent",
            message="Say whether this is a shop purchase, a customer sale, or a stock check.",
        )

    if quantity is not None and quantity < 0:
        return ParseDraft(
            intent=intent,
            product_query=product_query,
            quantity=quantity,
            unit=unit,
            sale_amount=amount,
            error_code="invalid_quantity",
            message="Quantity cannot be negative.",
        )

    if unit is not None and unit not in ALLOWED_UNITS:
        return ParseDraft(
            intent=intent,
            product_query=product_query,
            quantity=quantity,
            unit=unit,
            sale_amount=amount,
            error_code="invalid_unit",
            message="That unit is not supported.",
        )

    if intent in {"purchase_stock", "record_sale"}:
        if quantity is None:
            missing.append("quantity")
        if unit is None:
            missing.append("unit")
    if intent == "record_sale" and amount is None:
        missing.append("sale_amount")
    if not product_query:
        missing.append("product")

    if missing:
        message = "Need more information: " + ", ".join(missing) + "."
    elif intent == "check_stock":
        message = "Looking up stock."
    elif intent == "purchase_stock":
        message = "Ready to add purchased stock after confirmation."
    else:
        message = "Ready to record a sale after confirmation."

    return ParseDraft(
        intent=intent,
        product_query=product_query,
        quantity=quantity,
        unit=unit,
        sale_amount=amount,
        missing=missing,
        error_code=error_code,
        message=message,
    )
