"""Evidence-driven, non-destructive HVAC investigation workflow."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.facility.rag.service import FacilityRagService, build_grounded_context


class FacilityEvidenceTools(Protocol):
    def get_energy_consumption(self, asset_code: str) -> dict[str, Any]: ...
    def get_asset_status(self, asset_code: str) -> dict[str, Any]: ...
    def get_sensor_data(self, asset_code: str, metric: str | None = None) -> dict[str, Any]: ...
    def get_active_alerts(self, asset_code: str | None = None) -> dict[str, Any]: ...
    def get_asset_relationships(self, asset_code: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class HvacInvestigationResult:
    evidence: dict[str, Any]
    citations: list[dict[str, str]]
    likely_cause: str | None
    maintenance_recommended: bool
    next_action: str


class HvacInvestigationOrchestrator:
    """Combines MCP evidence and RAG procedure evidence without executing writes."""

    def __init__(self, tools: FacilityEvidenceTools, rag: FacilityRagService):
        self._tools = tools
        self._rag = rag

    def investigate(
        self, chiller_asset_code: str, ahu_asset_code: str,
    ) -> HvacInvestigationResult:
        energy = self._tools.get_energy_consumption(chiller_asset_code)
        ahu_status = self._tools.get_asset_status(ahu_asset_code)
        airflow = self._tools.get_sensor_data(ahu_asset_code, "airflow_cfm")
        alerts = self._tools.get_active_alerts(ahu_asset_code)
        relationships = self._tools.get_asset_relationships(chiller_asset_code)
        chunks = self._rag.retrieve("AHU low airflow troubleshooting procedure", top_k=2)
        _, citations = build_grounded_context(chunks)

        degraded = ahu_status.get("status") == "degraded"
        has_alert = bool(alerts.get("alerts"))
        readings = airflow.get("readings") or []
        low_airflow = bool(readings) and float(readings[0].get("value", 0)) > 0
        probable = degraded and has_alert and low_airflow
        likely_cause = None
        if probable:
            likely_cause = (
                f"{ahu_asset_code} is degraded with an active airflow alert; its low airflow is the most supported "
                "cause to investigate before treating elevated chiller power as the primary fault."
            )
        recommended = probable and bool(chunks)
        next_action = (
            "Ask the operator to confirm creation of a maintenance request."
            if recommended else "Report the available evidence and request more operator-approved diagnostics."
        )
        return HvacInvestigationResult(
            evidence={
                "chiller_energy": energy, "ahu_status": ahu_status, "ahu_airflow": airflow,
                "ahu_alerts": alerts, "asset_relationships": relationships,
            },
            citations=citations,
            likely_cause=likely_cause,
            maintenance_recommended=recommended,
            next_action=next_action,
        )
