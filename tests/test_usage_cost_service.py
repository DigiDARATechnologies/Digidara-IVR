import json
import os
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.services.usage_cost_service import (
    COST_ESTIMATION_VERSION,
    backfill_openai_cost_estimates,
    estimate_openai_cost_usd,
    provider_cost_summary,
    realtime_token_rates,
)


class UsageCostServiceTests(unittest.TestCase):
    def test_mini_cost_uses_discounted_cached_input_tokens(self):
        usage = {
            "input_audio": 6533,
            "output_audio": 2875,
            "input_text": 82670,
            "output_text": 3551,
            "cached_input_audio": 4480,
            "cached_input_text": 67008,
            "transcription_input_audio": 608,
            "transcription_output_text": 177,
        }
        cost = estimate_openai_cost_usd(
            usage, "gpt-realtime-2.1-mini", "english", "gpt-4o-mini-transcribe"
        )
        self.assertEqual(cost, Decimal("0.10402308"))

    def test_full_model_cost_uses_full_model_cached_rates(self):
        usage = {
            "input_audio": 10152,
            "output_audio": 4359,
            "input_text": 35305,
            "output_text": 2892,
            "cached_input_audio": 5120,
            "cached_input_text": 16896,
            "transcription_input_audio": 662,
            "transcription_output_text": 332,
        }
        cost = estimate_openai_cost_usd(
            usage, "gpt-realtime-2.1", "tamil", "gpt-4o-transcribe"
        )
        self.assertEqual(cost, Decimal("0.5991424"))

    def test_cached_tokens_are_clamped_to_total_input(self):
        usage = {
            "input_audio": 100,
            "cached_input_audio": 500,
            "input_text": 100,
            "cached_input_text": 500,
        }
        cost = estimate_openai_cost_usd(
            usage, "gpt-realtime-2.1-mini", "english", "gpt-4o-mini-transcribe"
        )
        self.assertEqual(cost, Decimal("0.000036"))

    def test_tamil_rate_override_wins_and_invalid_override_is_clear(self):
        with patch.dict(os.environ, {"OPENAI_AUDIO_INPUT_USD_PER_M_TAMIL": "12.5"}, clear=True):
            self.assertEqual(realtime_token_rates("gpt-realtime-2.1-mini", "tamil")["audio_input"], Decimal("12.5"))
        with patch.dict(os.environ, {"OPENAI_AUDIO_INPUT_USD_PER_M_TAMIL": "invalid"}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENAI_AUDIO_INPUT_USD_PER_M_TAMIL"):
                realtime_token_rates("gpt-realtime-2.1-mini", "tamil")

    def test_provider_costs_use_independent_inr_rates(self):
        with patch.dict(
            os.environ,
            {"USD_TO_INR_RATE": "96.16", "PLIVO_USD_TO_INR_RATE": "80"},
            clear=True,
        ):
            result = provider_cost_summary(Decimal("0.70316548"), Decimal("0.09"))
        self.assertEqual(result["openai_estimated_inr"], 67.62)
        self.assertEqual(result["plivo_recorded_inr"], 7.2)
        self.assertEqual(result["total_estimated_inr"], 74.82)

    def test_backfill_updates_usage_and_latest_call_cost_in_one_commit(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchall.return_value = [{
            "id": 7,
            "call_log_id": 3,
            "model_name": "gpt-realtime-2.1-mini",
            "input_audio_tokens": 100,
            "output_audio_tokens": 0,
            "input_text_tokens": 100,
            "output_text_tokens": 0,
            "cached_input_audio_tokens": 100,
            "cached_input_text_tokens": 100,
            "estimated_cost_usd": Decimal("0.001"),
            "usage_data": json.dumps({"transcription_input_audio": 0}),
            "language": "english",
            "transcription_model": "gpt-4o-mini-transcribe",
            "voice_style_profile": "english_concise_v1",
            "turn_gate_profile": "english_v1",
        }]

        result = backfill_openai_cost_estimates(db)

        self.assertEqual(result["usage_rows"], 1)
        self.assertEqual(result["call_logs"], 1)
        self.assertEqual(result["new_estimated_usd"], Decimal("0.000036"))
        db.commit.assert_called_once_with()
        db.rollback.assert_not_called()
        usage_update = cursor.execute.call_args_list[1]
        self.assertIn("UPDATE realtime_usage", usage_update.args[0])
        saved_usage = json.loads(usage_update.args[1][1])
        self.assertEqual(saved_usage["legacy_estimated_cost_usd"], 0.001)
        self.assertEqual(saved_usage["cost_estimation_version"], COST_ESTIMATION_VERSION)
        call_update = cursor.execute.call_args_list[2]
        self.assertIn("UPDATE call_logs", call_update.args[0])
        self.assertEqual(call_update.args[1], (Decimal("0.000036"), 3))


if __name__ == "__main__":
    unittest.main()
