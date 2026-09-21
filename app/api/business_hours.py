import pymysql
from fastapi import APIRouter, Depends

from app.api.auth import current_admin
from app.database.db import get_db
from app.schemas.business_hours import (
    BusinessHoursResponse,
    BusinessHoursSet,
    BusinessHoursStatus,
    DaySchedule,
)
from app.services import business_hours_service

router = APIRouter(dependencies=[Depends(current_admin)])


@router.get(
    "/business-hours",
    response_model=BusinessHoursResponse,
    summary="Get this organization's weekly business-hours schedule",
)
def read_business_hours(
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db),
):
    organization_id = admin["organization_id"]
    schedule = business_hours_service.get_schedule(db, organization_id)
    return BusinessHoursResponse(
        organization_id=organization_id,
        timezone=business_hours_service.get_organization_timezone(db, organization_id),
        configured=bool(schedule),
        days=[DaySchedule(**row) for row in schedule],
    )


@router.put(
    "/business-hours",
    response_model=BusinessHoursResponse,
    summary="Replace this organization's weekly business-hours schedule",
    description=(
        "Takes the full week (one entry per day 0-6) and the organization's "
        "IANA timezone, and atomically replaces any existing schedule. "
        "Inbound calls outside these hours are declined with a closed "
        "message instead of reaching the AI receptionist."
    ),
)
def update_business_hours(
    schedule_in: BusinessHoursSet,
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db),
):
    organization_id = admin["organization_id"]
    schedule = business_hours_service.set_schedule(db, organization_id, schedule_in)
    return BusinessHoursResponse(
        organization_id=organization_id,
        timezone=schedule_in.timezone,
        configured=True,
        days=[DaySchedule(**row) for row in schedule],
    )


@router.get(
    "/business-hours/status",
    response_model=BusinessHoursStatus,
    summary="Check whether this organization is open right now",
)
def read_business_hours_status(
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db),
):
    return business_hours_service.is_open_now(db, admin["organization_id"])
