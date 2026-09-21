"""Prepare a clear, normalized bilingual language-menu clip for telephony."""

from __future__ import annotations

import io
import math
import sys
import wave
from array import array


TELEPHONY_SAMPLE_RATE = 16000


def language_prompt_tts_payload(text: str) -> dict[str, object]:
    return {
        "model": "gpt-4o-mini-tts",
        "voice": "shimmer",
        "input": text,
        "instructions": (
            "Speak this bilingual phone menu clearly at a strong, consistent "
            "volume. Do not whisper. Use an easy-to-understand Indian phone-call "
            "delivery and pause briefly between the English and Tamil choices."
        ),
        "response_format": "wav",
        "speed": 0.9,
    }


def _resample_mono_pcm16(
    samples: array, source_rate: int, target_rate: int,
) -> array:
    if source_rate == target_rate or len(samples) < 2:
        return array("h", samples)
    output_length = max(1, round(len(samples) * target_rate / source_rate))
    output = array("h")
    scale = source_rate / target_rate
    last_index = len(samples) - 1
    for output_index in range(output_length):
        source_position = min(output_index * scale, last_index)
        lower = int(source_position)
        upper = min(lower + 1, last_index)
        fraction = source_position - lower
        value = round(samples[lower] + (samples[upper] - samples[lower]) * fraction)
        output.append(max(-32768, min(32767, value)))
    return output


def normalize_language_prompt_wav(
    wav_bytes: bytes,
    *,
    target_rms_dbfs: float = -16.0,
    peak_ceiling_dbfs: float = -1.0,
    max_gain: float = 3.0,
) -> bytes:
    """Return mono 16 kHz PCM WAV with stronger speech and no clipping."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        source_rate = source.getframerate()
        frames = source.readframes(source.getnframes())
    if channels != 1 or sample_width != 2:
        raise ValueError("Language prompt TTS must return mono 16-bit PCM WAV")

    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    samples = _resample_mono_pcm16(samples, source_rate, TELEPHONY_SAMPLE_RATE)
    if not samples:
        raise ValueError("Language prompt TTS returned empty audio")

    peak = max(abs(value) for value in samples)
    rms = math.sqrt(sum(value * value for value in samples) / len(samples))
    if peak == 0 or rms == 0:
        raise ValueError("Language prompt TTS returned silent audio")

    full_scale = 32767.0
    target_rms = full_scale * (10 ** (target_rms_dbfs / 20))
    peak_ceiling = full_scale * (10 ** (peak_ceiling_dbfs / 20))
    gain = min(max_gain, target_rms / rms, peak_ceiling / peak)
    normalized = array(
        "h",
        (
            max(-32768, min(32767, round(value * gain)))
            for value in samples
        ),
    )
    if sys.byteorder != "little":
        normalized.byteswap()

    output = io.BytesIO()
    with wave.open(output, "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(TELEPHONY_SAMPLE_RATE)
        destination.writeframes(normalized.tobytes())
    return output.getvalue()
