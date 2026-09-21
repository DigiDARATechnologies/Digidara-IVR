"""Defensive parsing and clear fallback summaries for completed voice calls."""

import json
import re
from typing import Any, Dict, Tuple


_UNKNOWN = {"", "n/a", "na", "none", "null", "unknown", "not applicable"}
_ACKNOWLEDGEMENTS = {
    "yes", "yeah", "ok", "okay", "sure", "no", "thanks", "thank you",
    "ஆம்", "ஆமா", "சரி", "ஓகே", "இல்ல", "இல்லை", "நன்றி",
}


def parse_analysis_response(raw: str) -> Dict[str, Any]:
    """Extract the first valid JSON object even when a provider adds fences/text."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


def _clean(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return "" if cleaned.lower() in _UNKNOWN else cleaned


def _speaker_turns(transcript: str, speakers: str) -> list[str]:
    turns: list[str] = []
    seen: set[str] = set()
    for raw_line in (transcript or "").splitlines():
        match = re.match(rf"\s*(?:{speakers})\s*:\s*(.+)", raw_line, re.IGNORECASE)
        if not match:
            continue
        text = re.sub(r"\s+", " ", match.group(1)).strip()
        normalized = text.casefold()
        if text and normalized not in seen:
            seen.add(normalized)
            turns.append(text)
    return turns


def _is_meaningful(text: str) -> bool:
    normalized = text.casefold().strip().rstrip(".!?")
    if not normalized or normalized in _ACKNOWLEDGEMENTS:
        return False
    closing_words = {"bye", "goodbye", "okay bye", "ok bye", "thank you bye", "thanks bye"}
    return normalized not in closing_words


def _shorten(text: str, limit: int = 300) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip(" ,;:-") + "…"


def _fallback_next_action(customer_turns: list[str]) -> str:
    joined = " ".join(customer_turns).casefold()
    if "visit" in joined:
        return "Share the location and arrange course counselling when the customer visits."
    if "contact" in joined or "team" in joined:
        return "The counselling team should provide batch, fee, and enrolment details when contacted."
    if "callback" in joined or "call back" in joined:
        return "A counsellor should call back and confirm the requested course details."
    return "No confirmed follow-up was captured; review the call before scheduling the next contact."


def fallback_summary(transcript: str, status: str) -> Tuple[str, str]:
    """Create a factual summary without inventing intent when analysis is unavailable."""
    customer_turns = _speaker_turns(transcript, "user|customer")
    assistant_turns = _speaker_turns(transcript, "assistant|ai assistant|ai")
    meaningful = [turn for turn in customer_turns if _is_meaningful(turn)]
    clean_status = _clean(status).replace("-", " ") or "completed"
    if not meaningful:
        summary = (
            "Customer need: No meaningful customer response was captured.\n"
            f"Outcome: Call status was {clean_status}.\n"
            "Next action: Review the recording or retry the call if appropriate."
        )
        return summary, "No meaningful customer response captured"

    need = max(meaningful, key=len)
    assistant_details = [
        turn for turn in assistant_turns
        if _is_meaningful(turn) and not turn.casefold().startswith(("welcome", "hello", "hi "))
    ]
    lines = [f"Customer need: {_shorten(need)}"]
    if assistant_details:
        lines.append(f"Discussion: {_shorten(max(assistant_details, key=len))}")
    final_position = meaningful[-1]
    if final_position == need:
        lines.append(f"Outcome: Call status was {clean_status}; no separate final decision was captured.")
    else:
        lines.append(f"Outcome: {_shorten(final_position)}")
    lines.append(f"Next action: {_fallback_next_action(customer_turns)}")
    summary = "\n".join(lines[:4])
    quick = f"Customer discussed: {_shorten(need, 145)}"
    return summary, quick[:180]


def build_call_summary(
    analysis: Dict[str, Any], transcript: str, status: str
) -> Tuple[str, str]:
    """Return three or four short, factual details for the History page."""
    fallback_full, fallback_quick = fallback_summary(transcript, status)
    customer_need = _clean(analysis.get("customer_need"))
    discussion = _clean(analysis.get("discussion"))
    outcome = _clean(analysis.get("outcome"))
    legacy_summary = _clean(analysis.get("summary"))
    quick = _clean(analysis.get("quick_summary"))
    next_action = _clean(analysis.get("next_action"))

    if not customer_need and len(legacy_summary) >= 20 and not legacy_summary.startswith("{"):
        customer_need = legacy_summary
    if customer_need:
        clean_status = _clean(status).replace("-", " ") or "completed"
        outcome_detail = outcome or f"Call status was {clean_status}."
        details = [f"Customer need: {customer_need}"]
        if discussion:
            details.append(f"Discussion: {discussion}")
        details.append(f"Outcome: {outcome_detail}")
        details.append(
            f"Next action: {next_action or 'No confirmed follow-up was captured.'}"
        )
        summary = "\n".join(details[:4])
    else:
        summary = fallback_full
    if len(quick) < 8 or quick.startswith("{"):
        quick = outcome or fallback_quick
    return summary[:4000], quick[:180]
