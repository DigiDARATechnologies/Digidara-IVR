"""Deterministic validation for Realtime telephone input turns."""

import math
import re
from dataclasses import dataclass
from typing import Iterable

from app.services.audio_utils import MULAW_TO_PCM


TAMIL_TURN_GATE_PROFILE = "tamil_fast_semantic_barge_in_v4"

_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u0B80-\u0BFF]+", re.UNICODE)
_NON_SPEECH_TRANSCRIPTS = {
    "",
    "music",
    "background music",
    "silence",
    "noise",
    "inaudible",
    "unintelligible",
}


@dataclass
class TurnAudioStats:
    duration_ms: int = 0
    peak_rms: float = 0.0
    average_rms: float = 0.0
    voiced_frames: int = 0
    total_frames: int = 0


def mulaw_rms(audio: bytes) -> float:
    if not audio:
        return 0.0
    return math.sqrt(
        sum(MULAW_TO_PCM[byte] * MULAW_TO_PCM[byte] for byte in audio) / len(audio)
    )


def caller_perceived_latency_ms(last_voiced_at: float, first_audio_at: float) -> int:
    """Measure response delay from the caller's last voiced audio frame."""
    return max(0, int((first_audio_at - last_voiced_at) * 1000))


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "")]


def looks_like_assistant_echo(transcript: str, assistant_text: str) -> bool:
    """Reject a caller-side transcription that is mostly the playing assistant."""
    heard = set(_tokens(transcript))
    spoken = set(_tokens(assistant_text))
    if len(heard) < 2 or not spoken:
        return False
    return len(heard & spoken) / len(heard) >= 0.80


def validate_turn(
    transcript: str,
    stats: TurnAudioStats,
    recent_assistant_text: str = "",
    *,
    minimum_duration_ms: int = 240,
    minimum_peak_rms: float = 240.0,
    minimum_voiced_frames: int = 3,
) -> tuple[bool, str]:
    """Return whether a committed VAD turn contains credible customer speech."""
    normalized = " ".join(_tokens(transcript))
    if normalized in _NON_SPEECH_TRANSCRIPTS:
        return False, "empty_or_non_speech_transcript"
    if stats.duration_ms < minimum_duration_ms:
        return False, "turn_too_short"
    if stats.peak_rms < minimum_peak_rms:
        return False, "audio_below_speech_level"
    if stats.voiced_frames < minimum_voiced_frames:
        return False, "insufficient_voiced_audio"
    if looks_like_assistant_echo(transcript, recent_assistant_text):
        return False, "assistant_echo"
    return True, "accepted"


def build_turn_stats(
    rms_frames: Iterable[float],
    duration_ms: int,
    voiced_threshold: float,
) -> TurnAudioStats:
    frames = list(rms_frames)
    return TurnAudioStats(
        duration_ms=max(0, int(duration_ms)),
        peak_rms=max(frames, default=0.0),
        average_rms=(sum(frames) / len(frames)) if frames else 0.0,
        voiced_frames=sum(value >= voiced_threshold for value in frames),
        total_frames=len(frames),
    )


def is_credible_barge_in(
    rms_frames: Iterable[float],
    *,
    voiced_threshold: float = 220.0,
    minimum_peak_rms: float = 260.0,
    minimum_voiced_frames: int = 3,
) -> bool:
    """Validate a short live audio window before interrupting Tamil playback.

    This intentionally uses audio only: the transcript is not available while
    the caller is still speaking. Full turn validation remains responsible for
    deciding whether the model should answer after the caller stops.
    """
    frames = list(rms_frames)
    if not frames or max(frames) < minimum_peak_rms:
        return False
    return sum(value >= voiced_threshold for value in frames) >= minimum_voiced_frames
