"""Tests for the authenticated Facility Operations MCP tool boundary."""

import asyncio
import unittest

from app.facility.application.facility_tools import FacilityToolService
from app.facility.mcp.server import build_facility_mcp_server


class _Repository:
    def get_asset_details(self, organization_id, asset_reference):
        if asset_reference != "Chiller-01":
            return None
        return {
            "id": 7, "asset_code": "Chiller-01", "name": "Chiller-01",
            "status": "operational", "site_name": "Building A", "site_code": "BLDG-A",
            "metadata": {"normal_power_kw": 100.0},
        }

    def list_sensor_data(self, organization_id, asset_reference, metric=None):
        return [{"sensor_code": "CHILLER-01-POWER", "metric": "power_kw", "value": 118.0, "unit": "kW"}]

    def list_active_alerts(self, organization_id):
        return [{"id": 3, "asset_id": 7, "title": "Chiller warning"}]

    def list_asset_relationships(self, organization_id, asset_reference):
        return [{"relationship_type": "supplies", "from_asset_code": "Chiller-01", "to_asset_code": "AHU-02"}]


class FacilityMcpTests(unittest.TestCase):
    def test_energy_evidence_calculates_baseline_delta_without_llm_inference(self):
        result = FacilityToolService(_Repository(), 42).get_energy_consumption("Chiller-01")
        self.assertEqual(18.0, result["percent_above_baseline"])
        self.assertEqual(118.0, result["measurement"]["value"])

    def test_unknown_asset_returns_explicit_absence(self):
        result = FacilityToolService(_Repository(), 42).get_sensor_data("Unknown-01")
        self.assertFalse(result["found"])
        self.assertEqual([], result["readings"])

    def test_mcp_server_registers_only_read_tools_before_confirmation_workflow_exists(self):
        server = build_facility_mcp_server(_Repository(), 42)
        names = {tool.name for tool in asyncio.run(server.list_tools())}
        self.assertEqual(
            {
                "get_asset_details", "get_asset_status", "get_sensor_data",
                "get_energy_consumption", "get_active_alerts", "get_asset_relationships",
            },
            names,
        )
        self.assertNotIn("create_service_request", names)

    def test_mcp_server_exposes_write_tool_only_with_an_authenticated_actor(self):
        server = build_facility_mcp_server(_Repository(), 42, actor_user_id=9)
        names = {tool.name for tool in asyncio.run(server.list_tools())}
        self.assertIn("create_service_request", names)


if __name__ == "__main__":
    unittest.main()
