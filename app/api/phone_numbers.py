from typing import List

import pymysql
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import current_admin
from app.database.db import get_db
from app.schemas.phone_number import PhoneNumberCreate, PhoneNumberResponse, PhoneNumberUpdate
from app.services import campaign_service, phone_number_service

router = APIRouter(dependencies=[Depends(current_admin)])


def _require_campaign_in_org(db: pymysql.Connection, campaign_id: int, organization_id: int) -> None:
    if not campaign_service.get_campaign_by_id(db, campaign_id, organization_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Campaign {campaign_id} does not exist in this organization.",
        )


@router.get(
    "/phone-numbers",
    response_model=List[PhoneNumberResponse],
    summary="List this organization's inbound-routed Plivo numbers",
)
def list_phone_numbers(
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db),
):
    return phone_number_service.list_for_organization(db, admin["organization_id"])


@router.post(
    "/phone-numbers",
    response_model=PhoneNumberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a Plivo DID for inbound routing",
    description=(
        "Maps a Plivo number your organization owns to a campaign, so "
        "/api/plivo/inbound routes calls dialed to that number here."
    ),
)
def create_phone_number(
    phone_number_in: PhoneNumberCreate,
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db),
):
    _require_campaign_in_org(db, phone_number_in.campaign_id, admin["organization_id"])
    try:
        return phone_number_service.create(db, admin["organization_id"], phone_number_in)
    except pymysql.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Number '{phone_number_in.plivo_number}' is already registered.",
        )


@router.patch(
    "/phone-numbers/{id}",
    response_model=PhoneNumberResponse,
    summary="Update a registered phone number's routing",
)
def update_phone_number(
    id: int,
    phone_number_in: PhoneNumberUpdate,
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db),
):
    if phone_number_in.campaign_id is not None:
        _require_campaign_in_org(db, phone_number_in.campaign_id, admin["organization_id"])
    updated = phone_number_service.update(db, id, admin["organization_id"], phone_number_in)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Phone number with ID {id} not found.",
        )
    return updated


@router.delete(
    "/phone-numbers/{id}",
    summary="Remove a phone number's inbound routing",
)
def delete_phone_number(
    id: int,
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db),
):
    success = phone_number_service.delete(db, id, admin["organization_id"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Phone number with ID {id} not found.",
        )
    return {"message": f"Phone number with ID {id} deleted successfully."}
