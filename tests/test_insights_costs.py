import os
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.api.insights import usage_summary


class InsightsCostPresentationTests(unittest.TestCase):
    def test_usage_summary_keeps_provider_costs_and_rates_separate(self):
        db = MagicMock()
        cursor = db.cursor.return_value
        cursor.fetchone.return_value = {
            "calls": 3,
            "seconds": 720,
            "tokens": 148337,
            "openai_usd": Decimal("0.70316548"),
            "telephony_usd": Decimal("0.09"),
        }
        cursor.fetchall.return_value = [{
            "id": 1,
            "name": "dhanush",
            "calls": 3,
            "seconds": 720,
            "tokens": 148337,
            "openai_usd": Decimal("0.70316548"),
            "telephony_usd": Decimal("0.09"),
        }]

        with patch.dict(
            os.environ,
            {"USD_TO_INR_RATE": "96.16", "PLIVO_USD_TO_INR_RATE": "80"},
            clear=False,
        ):
            result = usage_summary(admin={"organization_id": 9}, db=db)

        self.assertEqual(result["openai_estimated_inr"], 67.62)
        self.assertEqual(result["plivo_recorded_inr"], 7.2)
        self.assertEqual(result["total_estimated_inr"], 74.82)
        self.assertEqual(result["total_inr"], 74.82)
        self.assertEqual(result["customers"][0]["total_estimated_inr"], 74.82)
        self.assertEqual(cursor.execute.call_count, 2)


if __name__ == "__main__":
    unittest.main()
