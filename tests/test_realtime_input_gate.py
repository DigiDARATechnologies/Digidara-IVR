import unittest

from app.services.realtime_input_gate import (
    TAMIL_TURN_GATE_PROFILE,
    TurnAudioStats,
    build_turn_stats,
    caller_perceived_latency_ms,
    is_credible_barge_in,
    looks_like_assistant_echo,
    mulaw_rms,
    validate_turn,
)


class RealtimeInputGateTests(unittest.TestCase):
    def test_caller_perceived_latency_includes_vad_wait(self):
        self.assertEqual(caller_perceived_latency_ms(10.25, 13.75), 3500)
        self.assertEqual(caller_perceived_latency_ms(4.0, 3.0), 0)

    def test_mulaw_telephone_silence_has_zero_energy(self):
        self.assertEqual(mulaw_rms(bytes([0xFF]) * 160), 0.0)

    def test_rejects_silence_even_if_transcriber_returns_words(self):
        accepted, reason = validate_turn(
            "Thank you",
            TurnAudioStats(duration_ms=900, peak_rms=60, voiced_frames=0, total_frames=45),
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "audio_below_speech_level")

    def test_rejects_short_click_and_assistant_echo(self):
        accepted, reason = validate_turn(
            "ஆமா",
            TurnAudioStats(duration_ms=80, peak_rms=900, voiced_frames=4, total_frames=4),
        )
        self.assertFalse(accepted)
        self.assertEqual(reason, "turn_too_short")

        self.assertTrue(
            looks_like_assistant_echo(
                "இந்த course மூணு மாதம் online offline mode இருக்கு",
                "இந்த course மூணு மாதம். Online offline hybrid mode இருக்கு.",
            )
        )

    def test_accepts_real_short_tamil_reply_with_speech_energy(self):
        stats = build_turn_stats([120, 300, 520, 410, 280], 520, 220)
        accepted, reason = validate_turn("ஆமாங்க, சொல்லுங்க", stats)
        self.assertTrue(accepted)
        self.assertEqual(reason, "accepted")
        self.assertEqual(TAMIL_TURN_GATE_PROFILE, "tamil_fast_semantic_barge_in_v4")

    def test_live_barge_in_requires_sustained_voiced_audio(self):
        self.assertFalse(is_credible_barge_in([40, 55, 70, 60, 50]))
        self.assertFalse(is_credible_barge_in(
            [50, 900, 60, 55], minimum_voiced_frames=3
        ))
        self.assertTrue(is_credible_barge_in(
            [180, 260, 340, 510, 290],
            voiced_threshold=220,
            minimum_peak_rms=260,
            minimum_voiced_frames=3,
        ))


if __name__ == "__main__":
    unittest.main()
