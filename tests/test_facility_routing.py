"""Tests for LLM-first route selection and safe fallback behavior."""

import unittest

from app.facility.orchestration.routing import FacilityRouter


class FacilityRoutingTests(unittest.TestCase):
    def test_valid_high_confidence_classifier_output_is_used(self):
        router = FacilityRouter(lambda _: {"route": "diagnosis", "confidence": 0.91, "requires_confirmation": False})
        decision = router.route("Why did Chiller-01 fail?")
        self.assertEqual("diagnosis", decision.route)
        self.assertEqual("llm", decision.source)

    def test_invalid_classifier_output_falls_back_without_permitting_action(self):
        router = FacilityRouter(lambda _: {"route": "action", "confidence": "invalid"})
        decision = router.route("Create a maintenance request for AHU-02")
        self.assertEqual("action", decision.route)
        self.assertTrue(decision.requires_confirmation)
        self.assertEqual("safe_fallback", decision.source)

    def test_low_confidence_action_is_always_marked_for_confirmation(self):
        router = FacilityRouter(lambda _: {"route": "action", "confidence": 0.4, "requires_confirmation": False})
        decision = router.route("Create a service request")
        self.assertTrue(decision.requires_confirmation)

    def test_procedure_question_is_not_lost_to_llm_general_route(self):
        router = FacilityRouter(lambda _: {"route": "general", "confidence": 0.92, "requires_confirmation": False})
        decision = router.route("What should I check when an AHU has low airflow?")
        self.assertEqual("knowledge", decision.route)
        self.assertEqual("safety_guardrail", decision.source)
        self.assertFalse(decision.requires_confirmation)


if __name__ == "__main__":
    unittest.main()
