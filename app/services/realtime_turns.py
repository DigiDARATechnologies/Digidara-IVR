"""Pure helpers for Realtime/provider turn-state bookkeeping."""

import os
from typing import Optional


PCMU_BYTES_PER_MILLISECOND = 8
DEFAULT_PLAYBACK_MARK_INTERVAL_MS = 240


def playback_mark_name(item_id: str, audio_end_ms: int) -> str:
    """Encode a Realtime item and playback position in a provider checkpoint."""
    return f"rt|{item_id}|{max(0, int(audio_end_ms))}"


def parse_playback_mark(name: str) -> tuple[Optional[str], Optional[int]]:
    """Decode a mark created by playback_mark_name; ignore foreign marks."""
    if not name.startswith("rt|"):
        return None, None
    try:
        prefix, item_id, position = name.rsplit("|", 2)
        if prefix != "rt" or not item_id:
            return None, None
        return item_id, max(0, int(position))
    except (TypeError, ValueError):
        return None, None


def bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read an integer setting without letting a bad deployment value end calls."""
    raw_value = (os.getenv(name, str(default)) or str(default)).split("#", 1)[0].strip()
    try:
        value = int(raw_value)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def bounded_float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    """Read a float setting without letting a bad deployment value end calls."""
    raw_value = (os.getenv(name, str(default)) or str(default)).split("#", 1)[0].strip()
    try:
        value = float(raw_value)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))
