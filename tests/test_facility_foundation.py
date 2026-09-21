"""Regression tests for the Nectar facility domain foundation."""

import unittest
from datetime import datetime
from unittest.mock import MagicMock

from app.schemas.facility import FacilityOverviewOut
from app.services.facility_service import _row, get_facility_overview


class FacilityFoundationTests(unittest.TestCase):
    def test_row_decodes_safe_metadata_and_ignores_malformed_json(self):
        self.assertEqual({"source": "bms"}, _row({"metadata_json": '{"source":"bms"}'})["metadata"])
        self.assertEqual({}, _row({"metadata_json": "not-json"})["metadata"])

    def test_overview_is_organization_scoped_and_matches_contract(self):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [{"id": 1, "name": "Building A", "code": "BLDG-A", "timezone": "Asia/Kolkata"}],
            [{"id": 2, "site_id": 1, "asset_code": "AHU-02", "name": "AHU-02", "asset_type": "air_handling_unit", "status": "degraded", "location": "Third floor", "metadata_json": '{"design_airflow_cfm":12000}'}],
            [{"id": 3, "site_id": 1, "asset_id": 2, "severity": "high", "title": "AHU-02 low airflow", "message": "Below design", "status": "active", "opened_at": datetime(2026, 8, 19, 10, 0)}],
            [{"id": 4, "asset_id": 2, "sensor_code": "AHU-02-AIRFLOW", "metric": "airflow_cfm", "value": 7200, "unit": "cfm", "observed_at": datetime(2026, 8, 19, 10, 1)}],
            [],
        ]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        overview = get_facility_overview(conn, 42)

        parsed = FacilityOverviewOut.model_validate(overview)
        self.assertEqual("AHU-02", parsed.assets[0].asset_code)
        self.assertEqual(12000, parsed.assets[0].metadata["design_airflow_cfm"])
        self.assertEqual("high", parsed.active_alerts[0].severity)
        self.assertTrue(all(call.args[1] == (42,) for call in cursor.execute.call_args_list))


if __name__ == "__main__":
    unittest.main()
