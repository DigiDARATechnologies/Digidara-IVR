"""Application facade for the browser/operator Facility Agent surface."""

from app.facility.application.facility_tools import FacilityToolService
from app.facility.infrastructure.repository import FacilityRepository
from app.facility.orchestration.hvac_investigation import HvacInvestigationOrchestrator
from app.facility.orchestration.routing import FacilityRouter
from app.facility.rag.service import FacilityRagService, build_grounded_context


def answer_facility_query(repository: FacilityRepository, organization_id: int, message: str) -> dict:
    decision = FacilityRouter().route(message)
    rag = FacilityRagService()
    if decision.route == "knowledge":
        chunks = rag.retrieve(message)
        _, citations = build_grounded_context(chunks)
        if not chunks:
            reply = "I could not find sufficient approved facility documentation to answer that safely."
        else:
            reply = f"According to {chunks[0].citation.title}, {chunks[0].text}"
        return {"reply": reply, "route": decision.route, "route_source": decision.source, "citations": citations, "requires_confirmation": False}
    if decision.route == "diagnosis":
        assets = repository.list_assets(organization_id)
        chiller = next((asset["asset_code"] for asset in assets if asset["asset_type"] == "chiller"), None)
        ahu = next((asset["asset_code"] for asset in assets if asset["asset_type"] == "air_handling_unit"), None)
        if not chiller or not ahu:
            return {"reply": "I need a configured chiller and air-handling unit before I can investigate the HVAC issue.", "route": decision.route, "route_source": decision.source, "citations": [], "requires_confirmation": False}
        result = HvacInvestigationOrchestrator(FacilityToolService(repository, organization_id), rag).investigate(chiller, ahu)
        reply = result.likely_cause or "I could not establish a supported likely cause from the available facility evidence."
        return {"reply": reply, "route": decision.route, "route_source": decision.source, "citations": result.citations, "requires_confirmation": result.maintenance_recommended}
    if decision.route == "action":
        return {"reply": "I can prepare a maintenance request, but I need the target site, asset, and your explicit confirmation before creating it.", "route": decision.route, "route_source": decision.source, "citations": [], "requires_confirmation": True}
    overview = repository.list_assets(organization_id)
    return {"reply": f"I found {len(overview)} configured facility assets. Ask about a specific asset, current reading, or documented procedure.", "route": decision.route, "route_source": decision.source, "citations": [], "requires_confirmation": False}
