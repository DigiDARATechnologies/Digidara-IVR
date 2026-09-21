"""Regression evaluations required before a Facility router/policy change ships."""

import unittest

from app.facility.evaluation.scenarios import ROUTE_SCENARIOS, evaluate_safe_fallback


class FacilityEvaluationTests(unittest.TestCase):
    def test_safe_fallback_route_evaluation_set_passes(self):
        results = evaluate_safe_fallback()
        failures = [scenario.name for scenario, passed in results if not passed]
        self.assertEqual([], failures)
        self.assertEqual(len(ROUTE_SCENARIOS), len(results))


if __name__ == "__main__":
    unittest.main()
