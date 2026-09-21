import io
import math
import unittest
import wave
from array import array
from pathlib import Path

from app.services.language_prompt_audio import (
    TELEPHONY_SAMPLE_RATE,
    language_prompt_tts_payload,
    normalize_language_prompt_wav,
)


def _quiet_test_wav(sample_rate: int = 24000) -> bytes:
    samples = array(
        "h",
        (
            round(900 * math.sin(2 * math.pi * 440 * index / sample_rate))
            for index in range(sample_rate // 10)
        ),
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(samples.tobytes())
    return output.getvalue()


class LanguagePromptAudioTests(unittest.TestCase):
    def test_tts_request_is_clear_slow_and_strong(self):
        payload = language_prompt_tts_payload("Choose a language")
        self.assertEqual(payload["model"], "gpt-4o-mini-tts")
        self.assertEqual(payload["response_format"], "wav")
        self.assertEqual(payload["speed"], 0.9)
        self.assertIn("strong, consistent volume", payload["instructions"])
        self.assertIn("Do not whisper", payload["instructions"])

    def test_wav_is_normalized_resampled_and_not_clipped(self):
        normalized = normalize_language_prompt_wav(_quiet_test_wav())
        with wave.open(io.BytesIO(normalized), "rb") as source:
            self.assertEqual(source.getnchannels(), 1)
            self.assertEqual(source.getsampwidth(), 2)
            self.assertEqual(source.getframerate(), TELEPHONY_SAMPLE_RATE)
            samples = array("h")
            samples.frombytes(source.readframes(source.getnframes()))

        self.assertGreater(max(abs(value) for value in samples), 900)
        self.assertLessEqual(max(abs(value) for value in samples), 32767)

    def test_active_plivo_route_uses_versioned_wav(self):
        source = Path("app/api/plivo.py").read_text(encoding="utf-8")
        self.assertIn('"language_prompt_v2.wav"', source)
        self.assertIn('@router.get("/language-prompt-v2.wav")', source)
        self.assertIn('media_type="audio/wav"', source)


if __name__ == "__main__":
    unittest.main()
