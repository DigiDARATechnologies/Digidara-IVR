"""Tests for the non-destructive multi-step HVAC investigation workflow."""

import unittest

from app.facility.orchestration.hvac_investigation import HvacInvestigationOrchestrator
from app.facility.rag.service import FacilityCitation, FacilityRetrievedChunk


class _Tools:
    def get_energy_consumption(self, asset_code):
        return {"found": True, "percent_above_baseline": 18.0}

    def get_asset_status(self, asset_code):
        return {"found": True, "status": "degraded"}

    def get_sensor_data(self, asset_code, metric=None):
        return {"found": True, "readings": [{"metric": metric, "value": 7200, "unit": "cfm"}]}

    def get_active_alerts(self, asset_code=None):
        return {"found": True, "alerts": [{"severity": "high", "title": "AHU-02 low airflow"}]}

    def get_asset_relationships(self, asset_code):
        return {"found": True, "relationships": [{"relationship_type": "supplies", "to_asset_code": "AHU-02"}]}


class _Rag:
    def retrieve(self, query, top_k=3):
        return [FacilityRetrievedChunk(
            text="Verify filters and fan status.", distance=0.2,
            citation=FacilityCitation("hvac_low_airflow_v1", "AHU low-airflow troubleshooting procedure", "troubleshooting", "1.0"),
        )]


class HvacInvestigationTests(unittest.TestCase):
    def test_investigation_collects_multiple_evidence_sources_and_requires_confirmation(self):
        result = HvacInvestigationOrchestrator(_Tools(), _Rag()).investigate("Chiller-01", "AHU-02")

        self.assertIn("AHU-02", result.likely_cause)
        self.assertTrue(result.maintenance_recommended)
        self.assertIn("confirm", result.next_action.casefold())
        self.assertEqual("hvac_low_airflow_v1", result.citations[0]["source_id"])
        self.assertIn("chiller_energy", result.evidence)


if __name__ == "__main__":
    unittest.main()
