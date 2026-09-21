import unittest

from app.api.lead_score import generate_score, preview_score
from app.schemas.lead_score import LeadScoreRequest
from app.services.lead_scoring_policy import normalize_score, qualification_for_score


class LeadScoringPolicyTests(unittest.TestCase):
    def test_score_is_clamped_and_invalid_values_remain_unscored(self):
        self.assertEqual(100, normalize_score(125))
        self.assertEqual(0, normalize_score(-2))
        self.assertIsNone(normalize_score(None))
        self.assertIsNone(normalize_score("unknown"))

    def test_qualification_has_one_canonical_threshold_policy(self):
        cases = {None: None, 0: "unqualified", 19: "unqualified", 20: "cold", 49: "cold", 50: "warm", 79: "warm", 80: "hot", 100: "hot"}
        for score, expected in cases.items():
            with self.subTest(score=score):
                self.assertEqual(expected, qualification_for_score(score))

    def test_manual_calculator_is_explicitly_non_persisted_preview(self):
        value = LeadScoreRequest(
            interested=True, budget=True, decision_maker=False, callback_requested=False,
        )
        result = preview_score(value)
        self.assertEqual("manual_preview", result["source"])
        self.assertFalse(result["persisted"])
        self.assertEqual(result, generate_score(value))


if __name__ == "__main__":
    unittest.main()
