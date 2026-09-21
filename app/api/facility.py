"""Authenticated Facility Operations API foundation for the Nectar product."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import current_admin
from app.database.db import get_db
from app.facility.application.demo_scenario import seed_demo_facility
from app.facility.application.agent_query import answer_facility_query
from app.facility.application.facility_queries import get_facility_overview
from app.facility.application.service_request_actions import (
    FacilityActionError,
    FacilityActionService,
    FacilityActionValidationError,
)
from app.facility.domain.contracts import (
    ActionConfirmationOut,
    DemoFacilitySeedOut,
    FacilityOverviewOut,
    FacilityServiceRequestOut,
    FacilityAgentQueryInput,
    FacilityAgentResponse,
    ServiceRequestDraftInput,
)
from app.facility.infrastructure.repository import FacilityRepository


router = APIRouter(prefix="/facility", tags=["Facility Operations"])


@router.get("/overview", response_model=FacilityOverviewOut)
def facility_overview(admin: dict[str, Any] = Depends(current_admin), db: Any = Depends(get_db)):
    """Read the signed-in organization's facility state; no cross-tenant access."""
    return get_facility_overview(FacilityRepository(db), admin["organization_id"])


@router.post("/demo/seed", response_model=DemoFacilitySeedOut, status_code=status.HTTP_201_CREATED)
def seed_facility_demo(admin: dict[str, Any] = Depends(current_admin), db: Any = Depends(get_db)):
    """Create the non-destructive Building A demo data used in the challenge."""
    return seed_demo_facility(FacilityRepository(db), admin["organization_id"])


@router.post("/agent/query", response_model=FacilityAgentResponse)
def query_facility_agent(
    query: FacilityAgentQueryInput, admin: dict[str, Any] = Depends(current_admin), db: Any = Depends(get_db),
):
    """Return a grounded agent result for the facility operator console."""
    return answer_facility_query(FacilityRepository(db), admin["organization_id"], query.message)


@router.post("/actions/service-requests/prepare", response_model=ActionConfirmationOut, status_code=status.HTTP_202_ACCEPTED)
def prepare_service_request(
    draft: ServiceRequestDraftInput, admin: dict[str, Any] = Depends(current_admin), db: Any = Depends(get_db),
):
    """Persist a proposed operational action; this endpoint creates no work order."""
    try:
        return FacilityActionService(FacilityRepository(db), admin["organization_id"], admin["id"]).prepare_service_request(draft)
    except FacilityActionValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/actions/service-requests/{confirmation_id}/confirm", response_model=FacilityServiceRequestOut)
def confirm_service_request(
    confirmation_id: str, admin: dict[str, Any] = Depends(current_admin), db: Any = Depends(get_db),
):
    """Consume a single explicit confirmation and create exactly one work order."""
    try:
        return FacilityActionService(FacilityRepository(db), admin["organization_id"], admin["id"]).confirm_and_create_service_request(confirmation_id)
    except FacilityActionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
