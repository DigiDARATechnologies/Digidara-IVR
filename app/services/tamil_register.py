"""Adaptive spoken-register guidance for Tamil voice turns."""

from __future__ import annotations

import re
from typing import Literal


TamilRegister = Literal["tamil", "tanglish", "mixed"]

_TAMIL_CHAR_RE = re.compile(r"[\u0b80-\u0bff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def detect_tamil_register(transcript: str) -> TamilRegister:
    """Classify the transcript conservatively for response-style mirroring."""
    text = (transcript or "").strip()
    lowered = text.casefold()
    if any(phrase in lowered for phrase in ("தமிழ்ல பேச", "தமிழில் பேச", "pure tamil")):
        return "tamil"
    if any(phrase in lowered for phrase in ("tanglish", "english mix", "mix பண்ணி")):
        return "tanglish"

    tamil_chars = len(_TAMIL_CHAR_RE.findall(text))
    latin_words = len(_LATIN_WORD_RE.findall(text))
    if tamil_chars and latin_words >= 3:
        return "mixed"
    if tamil_chars:
        return "tamil"
    return "tanglish"


def tamil_register_instruction(transcript: str) -> str:
    """Return audio-response guidance without changing factual behavior."""
    register = detect_tamil_register(transcript)
    shared = (
        "Infer the caller's actual spoken register from the audio as the primary "
        "signal; use the transcript only as a hint because Tamil STT may rewrite "
        "spoken Tanglish in Tamil script. Keep a clear Tamil Nadu pronunciation. "
    )
    if register == "tamil":
        return (
            shared
            + "Reply mainly in natural spoken Tamil. Use English only for familiar "
            "course/technology terms the caller would normally use; avoid unnecessary "
            "English sentences and avoid formal literary Tamil."
        )
    if register == "mixed":
        return (
            shared
            + "Reply in balanced spoken Tamil/Tanglish, lightly matching the caller's "
            "mix. Keep Tamil grammar natural and do not increase the amount of English "
            "beyond the caller's style."
        )
    return (
        shared
        + "Reply in natural Tamil Nadu Tanglish with Tamil sentence structure and "
        "familiar English course/technology words. Do not switch to fully English, "
        "and do not use awkward word-by-word romanized pronunciation."
    )
