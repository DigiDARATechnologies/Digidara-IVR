"""Read-only use cases exposed by the Facility MCP server.

These use cases return evidence, not LLM-generated interpretations. The
orchestrator is responsible for combining the evidence with RAG procedures.
"""

from typing import Any

from app.facility.infrastructure.repository import FacilityRepository


class FacilityToolService:
    def __init__(self, repository: FacilityRepository, organization_id: int):
        if organization_id <= 0:
            raise ValueError("organization_id must be a positive authenticated tenant identifier")
        self._repository = repository
        self._organization_id = organization_id

    def get_asset_details(self, asset_code: str) -> dict[str, Any]:
        asset = self._repository.get_asset_details(self._organization_id, asset_code)
        return {"found": bool(asset), "asset": asset}

    def get_asset_status(self, asset_code: str) -> dict[str, Any]:
        result = self.get_asset_details(asset_code)
        asset = result["asset"]
        if not asset:
            return result
        return {
            "found": True,
            "asset_code": asset["asset_code"],
            "status": asset["status"],
            "site": {"name": asset["site_name"], "code": asset["site_code"]},
        }

    def get_sensor_data(self, asset_code: str, metric: str | None = None) -> dict[str, Any]:
        asset = self._repository.get_asset_details(self._organization_id, asset_code)
        if not asset:
            return {"found": False, "asset": None, "readings": []}
        return {
            "found": True,
            "asset": {"asset_code": asset["asset_code"], "name": asset["name"]},
            "readings": self._repository.list_sensor_data(self._organization_id, asset_code, metric),
        }

    def get_energy_consumption(self, asset_code: str) -> dict[str, Any]:
        asset = self._repository.get_asset_details(self._organization_id, asset_code)
        if not asset:
            return {"found": False, "asset": None, "measurement": None}
        readings = self._repository.list_sensor_data(self._organization_id, asset_code, "power_kw")
        if not readings:
            return {"found": True, "asset_code": asset["asset_code"], "measurement": None}
        current = float(readings[0]["value"])
        baseline = asset["metadata"].get("normal_power_kw")
        percent_above_baseline = None
        if isinstance(baseline, (int, float)) and baseline > 0:
            percent_above_baseline = round(((current - baseline) / baseline) * 100, 2)
        return {
            "found": True,
            "asset_code": asset["asset_code"],
            "measurement": readings[0],
            "normal_power_kw": baseline,
            "percent_above_baseline": percent_above_baseline,
        }

    def get_active_alerts(self, asset_code: str | None = None) -> dict[str, Any]:
        alerts = self._repository.list_active_alerts(self._organization_id)
        if not asset_code:
            return {"alerts": alerts}
        asset = self._repository.get_asset_details(self._organization_id, asset_code)
        if not asset:
            return {"found": False, "alerts": []}
        return {"found": True, "alerts": [alert for alert in alerts if alert["asset_id"] == asset["id"]]}

    def get_asset_relationships(self, asset_code: str) -> dict[str, Any]:
        asset = self._repository.get_asset_details(self._organization_id, asset_code)
        if not asset:
            return {"found": False, "relationships": []}
        return {
            "found": True,
            "asset_code": asset["asset_code"],
            "relationships": self._repository.list_asset_relationships(self._organization_id, asset_code),
        }
