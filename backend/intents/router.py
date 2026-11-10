"""Conversational routes. Greeting is never the unknown-question fallback."""

from __future__ import annotations

import re

from validate import normalize_text

_GREET_EXACT = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "yo",
        "namaste",
        "namaskar",
        "good morning",
        "good evening",
        "good afternoon",
        "good night",
        "thanks",
        "thank you",
        "thank u",
        "ok",
        "okay",
        "who are you",
        "what can you do",
        "what do you do",
        "how are you",
        "hello how are you",
        "hi how are you",
        "धन्यवाद",
        "शुक्रिया",
        "नमस्ते",
        "नमस्कार",
        "आप कैसे हो",
        "आप कैसे हैं",
        "कैसे हो",
        "कैसे हैं",
        "ठीक है",
        "ನಮಸ್ಕಾರ",
        "ಧನ್ಯವಾದ",
        "ಹೇಗಿದ್ದೀರಿ",
        "नमस्कार",
        "कसे आहात",
        "आभार",
        "ठीक आहे",
    }
)

_GREET_PREFIX = (
    "good morning",
    "good evening",
    "good afternoon",
    "hello ",
    "hi ",
    "hey ",
    "namaste",
    "नमस्ते",
    "नमस्कार",
    "ನಮಸ್ಕಾರ",
)

_LANG_Q = (
    "do you speak",
    "do you understand",
    "can you speak",
    "can you understand",
    "which languages",
    "कौन सी भाषा",
    "बोलते हो",
    "समझते हो",
    "ಬರುತ್ತದೆಯಾ",
    "येते का",
)

_ADVICE = (
    "improve my sales",
    "improve sales",
    "how can i increase",
    "how can i improve",
    "business advice",
    "बिक्री कैसे बढ़ा",
    "ಮಾರಾಟ ಹೆಚ್ಚಿಸ",
    "विक्री वाढव",
)


def is_greeting(transcript: str) -> bool:
    raw = (transcript or "").strip()
    n = normalize_text(raw)
    folded = (raw or "").strip()
    if not n and not folded:
        return False
    if re.search(r"stock|sale|remind|purchase|बिक्री|स्टॉक|रिमाइंड|ಮಾರಾಟ|ಸ್ಟಾಕ್|विक्री", raw + n, re.I):
        return False
    compact = re.sub(r"[,.!?؟]+", " ", (n or folded))
    compact = re.sub(r"\s+", " ", compact).strip().lower()
    words = compact.split() if compact else folded.split()
    if len(words) > 8:
        return False
    if compact in _GREET_EXACT or n in _GREET_EXACT or folded in _GREET_EXACT:
        return True
    if any((compact or n).startswith(p) for p in _GREET_PREFIX) and len(words) <= 6:
        return True
    if re.fullmatch(r"(hello|hi|hey|namaste)([!., ]+.*)?", compact or n) and len(words) <= 6:
        return True
    return False


def rule_route(transcript: str) -> str | None:
    raw = transcript or ""
    n = normalize_text(raw)
    if not n and not raw.strip():
        return None
    if is_greeting(raw):
        return "general_conversation"
    if any(p in n or p in raw for p in _ADVICE):
        return "business_advice"
    if any(p in n or p in raw.lower() for p in _LANG_Q):
        return "general_question"
    if re.search(
        r"\b(what is|what's|who is|explain|difference between|differ(?:ence)?|how does|why is)\b|"
        r"क्या है|समझाओ|बताओ|बताइए|डिफरेंस|फर्क|अंतर|ಏನು|काय आहे",
        n + " " + raw,
        re.I,
    ) and not re.search(r"\b(sale|stock|बिक्री|ಮಾರಾಟ|विक्री|स्टॉक|inventory)\b", n + raw, re.I):
        return "general_question"
    return None


def greeting_reply(transcript: str, lang: str) -> str:
    n = normalize_text(transcript or "")
    morning = "morning" in n or "सुबह" in (transcript or "") or "ಬೆಳಿಗ್ಗೆ" in (transcript or "")
    if lang == "hi":
        if morning:
            return "सुबह बखैर। आज दुकान कैसी चल रही है?"
        if "thank" in n or "धन्यवाद" in (transcript or "") or "शुक्रिया" in (transcript or ""):
            return "जी, शुक्रिया। और कुछ बताइए।"
        return "नमस्ते। आज दुकान के लिए क्या करूँ — स्टॉक, बिक्री, या कोई सवाल?"
    if lang == "kn":
        if "thank" in n or "ಧನ್ಯವಾದ" in (transcript or ""):
            return "ಧನ್ಯವಾದ. ಇನ್ನೇನಾದರೂ ಹೇಳಿ."
        return "ನಮಸ್ಕಾರ. ಇಂದು ಅಂಗಡಿಗೆ ಏನು ಬೇಕು — ಸ್ಟಾಕ್, ಮಾರಾಟ, ಅಥವಾ ಪ್ರಶ್ನೆ?"
    if lang == "mr":
        if "thank" in n or "आभार" in (transcript or ""):
            return "आभार. आणखी काही सांगा."
        return "नमस्कार. आज दुकानासाठी काय करू — स्टॉक, विक्री, की एखादा प्रश्न?"
    if morning:
        return "Good morning. How is the shop doing today?"
    if "thank" in n:
        return "You're welcome. What else can I help with?"
    return "Hello. How can I help the shop today — stock, sales, or a question?"


def unknown_question_reply(lang: str) -> str:
    if lang == "hi":
        return "समझ नहीं आया। स्टॉक, बिक्री, रिमाइंडर, या सामान्य सवाल कहें।"
    if lang == "kn":
        return "ಸ್ಪಷ್ಟವಾಗಿಲ್ಲ. ಸ್ಟಾಕ್, ಮಾರಾಟ, ಜ್ಞಾಪನೆ ಅಥವಾ ಸಾಮಾನ್ಯ ಪ್ರಶ್ನೆ ಹೇಳಿ."
    if lang == "mr":
        return "समजले नाही. स्टॉक, विक्री, रिमाइंडर किंवा सामान्य प्रश्न सांगा."
    return "I didn't catch a shop action. You can ask about stock, sales, a reminder, or a general question."


def llm_unavailable_reply(lang: str, code: str | None = None) -> str:
    if lang == "hi":
        return "भाषा मॉडल अभी जवाब नहीं दे पाया।"
    if lang == "kn":
        return "ಭಾಷಾ ಮಾದರಿ ಈಗ ಉತ್ತರಿಸಲಿಲ್ಲ."
    if lang == "mr":
        return "भाषा मॉडेल आत्ता उत्तर देऊ शकले नाही."
    return "The language model could not answer just now."


def general_offline_reply(lang: str) -> str:
    if lang == "hi":
        return "सामान्य ज्ञान के लिए भाषा मॉडल चाहिए। अभी वह उपलब्ध नहीं है। स्टॉक या बिक्री पूछ सकते हैं।"
    if lang == "kn":
        return "ಸಾಮಾನ್ಯ ಜ್ಞಾನಕ್ಕೆ ಭಾಷಾ ಮಾದರಿ ಬೇಕು. ಈಗ ಅದು ಲಭ್ಯವಿಲ್ಲ. ಸ್ಟಾಕ್ ಅಥವಾ ಮಾರಾಟ ಕೇಳಬಹುದು."
    if lang == "mr":
        return "सामान्य ज्ञानासाठी भाषा मॉडेल लागते. आत्ता ते उपलब्ध नाही. स्टॉक किंवा विक्री विचारू शकता."
    return "General questions need the language model, which is not available right now. You can still ask about stock or sales."


def fallback_chat(route: str, transcript: str, lang: str) -> str:
    if route == "business_advice":
        if lang == "hi":
            return "बिक्री बढ़ाने के सामान्य सुझाव: रोज़ाना टॉप आइटम देखें, स्टॉक खत्म न होने दें, और नियमित ग्राहकों को याद दिलाएँ। आँकड़े तभी बताऊँगा जब रिकॉर्ड में हों।"
        if lang == "kn":
            return "ಮಾರಾಟ ಹೆಚ್ಚಿಸಲು: ದಿನದ ಟಾಪ್ ವಸ್ತು ನೋಡಿ, ಸ್ಟಾಕ್ ಮುಗಿಯದಂತೆ ನೋಡಿಕೊಳ್ಳಿ. ಅಂಕಿ ಇದ್ದಾಗ ಮಾತ್ರ ಹೇಳುತ್ತೇನೆ."
        if lang == "mr":
            return "विक्री वाढवण्यासाठी: रोज टॉप माल पाहा, स्टॉक संपू देऊ नका. नोंदी असतील तरच आकडे सांगेन."
        return (
            "General ways to improve sales: watch today's top items, avoid stockouts, "
            "and follow up with regular customers. I only quote figures that are in your records."
        )
    if route == "general_question":
        n = normalize_text(transcript or "")
        if any(p in n or p in (transcript or "") for p in _LANG_Q):
            if lang == "hi":
                return "हाँ, मैं हिंदी, अंग्रेज़ी, कन्नड़ और मराठी समझ सकता हूँ। दुकान के काम और सामान्य बात दोनों कर सकते हैं।"
            if lang == "kn":
                return "ಹೌದು, ಕನ್ನಡ, ಇಂಗ್ಲಿಷ್, ಹಿಂದಿ, ಮರಾಠಿ ಅರ್ಥವಾಗುತ್ತದೆ."
            if lang == "mr":
                return "हो, मला मराठी, हिंदी, इंग्रजी आणि कन्नड समजते."
            return "Yes. I understand English, Hindi, Kannada, and Marathi."
        return general_offline_reply(lang)
    if route == "general_conversation":
        return greeting_reply(transcript, lang)
    return unknown_question_reply(lang)
