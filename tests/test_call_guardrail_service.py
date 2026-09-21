import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.call_guardrail_service import (
    call_duration_limit_seconds,
    evaluate_call_guardrails,
)
from app.services.telephony.base import CreateCallResult
from app.services.telephony_service import start_outbound_call


class CallGuardrailServiceTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "CALL_MAX_DURATION_SECONDS": "900",
            "CALL_ESTIMATED_COST_ALERT_INR": "50",
            "CALL_ESTIMATED_COST_PER_MINUTE_ALERT_INR": "8",
            "CALL_TURNS_PER_MINUTE_ALERT": "8",
            "CALL_INTERRUPTION_ALERT_COUNT": "5",
            "CALL_FALSE_TURN_ALERT_COUNT": "3",
            "USD_TO_INR_RATE": "96.16",
            "PLIVO_USD_TO_INR_RATE": "80",
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_normal_call_has_metrics_without_alerts(self):
        result = evaluate_call_guardrails({
            "duration": 300,
            "total_turns": 20,
            "interruption_count": 2,
            "false_turn_count": 1,
            "estimated_openai_cost_usd": 0.2,
            "estimated_telephony_cost_usd": 0.04,
        })
        self.assertEqual(result["turns_per_minute"], 4.0)
        self.assertEqual(result["interruptions_per_minute"], 0.4)
        self.assertEqual(result["estimated_cost_per_minute_inr"], 4.49)
        self.assertFalse(result["is_abnormal"])
        self.assertEqual(result["abnormal_reasons"], [])

    def test_expensive_high_activity_call_reports_each_reason(self):
        result = evaluate_call_guardrails({
            "duration": 900,
            "total_turns": 120,
            "interruption_count": 6,
            "false_turn_count": 3,
            "estimated_openai_cost_usd": 1.2,
            "estimated_telephony_cost_usd": 0.2,
            "provider_metadata": '{"time_limit_seconds": 900}',
        })
        self.assertTrue(result["is_abnormal"])
        self.assertEqual(result["call_duration_limit_seconds"], 900)
        self.assertEqual(set(result["abnormal_reasons"]), {
            "maximum_duration_reached",
            "high_estimated_total_cost",
            "high_estimated_cost_per_minute",
            "high_turn_rate",
            "repeated_interruptions",
            "repeated_false_turns",
        })

    def test_zero_duration_does_not_divide_or_raise_rate_alerts(self):
        result = evaluate_call_guardrails({
            "duration": 0,
            "total_turns": 100,
            "estimated_openai_cost_usd": 1,
        })
        self.assertEqual(result["turns_per_minute"], 0)
        self.assertEqual(result["estimated_cost_per_minute_inr"], 0)
        self.assertIn("high_estimated_total_cost", result["abnormal_reasons"])
        self.assertNotIn("high_turn_rate", result["abnormal_reasons"])

    def test_duration_limit_is_bounded_and_invalid_values_are_rejected(self):
        with patch.dict(os.environ, {"CALL_MAX_DURATION_SECONDS": "10"}):
            self.assertEqual(call_duration_limit_seconds(), 60)
        with patch.dict(os.environ, {"CALL_MAX_DURATION_SECONDS": "999999"}):
            self.assertEqual(call_duration_limit_seconds(), 86400)
        with patch.dict(os.environ, {"CALL_MAX_DURATION_SECONDS": "invalid"}):
            with self.assertRaisesRegex(ValueError, "must be an integer"):
                call_duration_limit_seconds()

    def test_shared_outbound_path_passes_duration_limit_to_provider(self):
        db = MagicMock()
        provider = MagicMock()
        provider.name = "plivo"
        provider.is_configured.return_value = True
        provider.create_call.return_value = CreateCallResult(
            provider="plivo", request_id="request-1", metadata={"api_id": "api-1"}
        )
        with (
            patch("app.services.telephony_service._reload_env"),
            patch("app.services.telephony_service._public_base_url", return_value="https://voice.test"),
            patch("app.services.telephony_service.get_telephony_provider", return_value=provider),
            patch("app.services.telephony_service.is_suppressed", return_value=False),
            patch("app.services.telephony_service.call_log_service.find_active_call", return_value=None),
            patch("app.services.telephony_service.call_log_service.create_call_log", return_value={"id": 7}),
            patch("app.services.telephony_service.call_log_service.get_call_log_by_id", return_value={"id": 7}),
        ):
            result = start_outbound_call(db, 9, 1, "9876543210", 2)

        self.assertEqual(result["status"], "initiated")
        self.assertEqual(provider.create_call.call_args.kwargs["time_limit_seconds"], 900)
        metadata_json = db.cursor.return_value.execute.call_args_list[-1].args[1][3]
        self.assertIn('"time_limit_seconds": 900', metadata_json)


if __name__ == "__main__":
    unittest.main()
