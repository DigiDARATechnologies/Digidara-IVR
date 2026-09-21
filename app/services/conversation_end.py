"""Conservative English/Tamil customer-farewell detection for voice calls."""

from __future__ import annotations

import re


_EXACT_ENDINGS = {
    "bye",
    "bye bye",
    "goodbye",
    "good bye",
    "thank you bye",
    "thanks bye",
    "okay bye",
    "ok bye",
    "thats all bye",
    "that is all bye",
    "talk to you later",
    "call me later bye",
    "பை",
    "பை பை",
    "நன்றி பை",
    "சரி பை",
    "சரிங்க பை",
    "சரிங்க நன்றி பை",
    "நன்றி வணக்கம்",
    "சரி நன்றி வணக்கம்",
    "அப்புறம் பேசலாம்",
    "போன் வைக்கிறேன்",
    "கால் கட் பண்ணுங்க",
    "முடிச்சுக்கலாம்",
    "nandri bye",
    "seri bye",
    "saringa bye",
    "apram pesalam",
    "phone vaikren",
    "call cut pannunga",
}

_EXPLICIT_PATTERNS = (
    r"\b(?:bye|goodbye|good\s+bye)\b",
    r"\b(?:end|cut|disconnect)\s+(?:the\s+)?call\b",
    r"\b(?:won'?t\s+you|will\s+you|can\s+you)\s+(?:cut|end|disconnect)\s+(?:the\s+)?call\b",
    r"\b(?:i\s+have\s+to\s+go|i(?:'| a)?m\s+going\s+now)\b",
    r"\b(?:phone|call)\s+(?:vaikren|vechudren|cut\s+pannu\w*)\b",
    r"(?:போன்|கால்).{0,12}(?:வைக்கிறேன்|வச்சிடுறேன்|கட்\s*பண்ணு)",
    # Negative-question "won't you cut/end it" and polite "will/can you cut it"
    # forms, e.g. "கட்பணமாட்டியா", "கட் பண்ணுங்களா", "call cut பண்ணலாமா".
    r"கட்.{0,8}மாட்டிய",
    r"(?:கால்|call).{0,4}கட்.{0,10}(?:பண்ணுங்களா|பண்ணலாமா)",
    r"(?:அப்புறம்|பிறகு).{0,8}(?:பேசலாம்|பேசுறேன்)",
)


def _normalize(text: str) -> str:
    normalized = (text or "").casefold().replace("’", "'")
    normalized = re.sub(r"[^\w\u0b80-\u0bff']+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def is_customer_goodbye(text: str, language: str = "english") -> bool:
    """Return true only for an explicit intent to finish the current call.

    A standalone "thank you" / "நன்றி" is deliberately not treated as an end:
    callers often thank the assistant and continue with another question.
    """
    normalized = _normalize(text)
    if not normalized or normalized in {
        "thank you", "thanks", "thank you so much", "நன்றி", "ரொம்ப நன்றி",
        "nandri", "romba nandri",
    }:
        return False
    if normalized in _EXACT_ENDINGS:
        return True
    if re.search(r"(?:^|\s)பை(?:\s|$)", normalized):
        return True
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in _EXPLICIT_PATTERNS)


def farewell_instruction(language: str) -> str:
    """Model instruction for the final assistant turn."""
    if (language or "").lower() == "tamil":
        return (
            "The customer has clearly ended the conversation. Give one short, warm "
            "Tamil/Tanglish farewell such as 'சரிங்க, நேரம் ஒதுக்கி பேசினதுக்கு "
            "ரொம்ப நன்றி. நல்ல நாளா இருக்கட்டும், பைங்க.' Do not ask a question, "
            "restart the sales pitch, introduce yourself, or add new information."
        )
    return (
        "The customer has clearly ended the conversation. Give one short, warm "
        "farewell such as 'Thank you for your time. Have a great day, goodbye.' "
        "Do not ask a question, restart the sales pitch, introduce yourself, or "
        "add new information."
    )
