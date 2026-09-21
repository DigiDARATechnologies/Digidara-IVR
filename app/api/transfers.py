from __future__ import annotations

import os
import re
import uuid
from urllib.parse import urlencode

import pymysql
from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.auth import current_admin
from app.database.db import get_db
from app.schemas.transfer import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    StaffDestinationCreate,
    StaffDestinationResponse,
    StaffDestinationUpdate,
    TransferRequest,
    TransferResponse,
)
from app.services import call_log_service, transfer_service
from app.services.telephony import get_telephony_provider


router = APIRouter(prefix="/transfers", tags=["Human Transfer"], dependencies=[Depends(current_admin)])


@router.get("/departments", response_model=list[DepartmentResponse])
def get_departments(active_only: bool = False, admin=Depends(current_admin), db=Depends(get_db)):
    return transfer_service.list_departments(db, admin["organization_id"], active_only)


@router.post("/departments", response_model=DepartmentResponse, status_code=201)
def create_department(
    value: DepartmentCreate, admin=Depends(current_admin), db=Depends(get_db),
):
    try:
        return transfer_service.create_department(
            db, admin["organization_id"], value.model_dump(),
        )
    except pymysql.IntegrityError as exc:
        raise HTTPException(409, "A department with this name already exists") from exc


@router.patch("/departments/{department_id}", response_model=DepartmentResponse)
def update_department(
    department_id: int, value: DepartmentUpdate,
    admin=Depends(current_admin), db=Depends(get_db),
):
    try:
        dept = transfer_service.update_department(
            db, admin["organization_id"], department_id,
            value.model_dump(exclude_unset=True),
        )
    except pymysql.IntegrityError as exc:
        raise HTTPException(409, "A department with this name already exists") from exc
    if not dept:
        raise HTTPException(404, "Department not found")
    return dept


@router.delete("/departments/{department_id}", status_code=204)
def delete_department(
    department_id: int, admin=Depends(current_admin), db=Depends(get_db),
):
    deleted = transfer_service.delete_department(
        db, admin["organization_id"], department_id,
    )
    if not deleted:
        raise HTTPException(404, "Department not found")


@router.get("/destinations", response_model=list[StaffDestinationResponse])
def destinations(active_only: bool = False, admin=Depends(current_admin), db=Depends(get_db)):
    return transfer_service.list_destinations(db, admin["organization_id"], active_only)


@router.post("/destinations", response_model=StaffDestinationResponse, status_code=201)
def create_destination(
    value: StaffDestinationCreate, admin=Depends(current_admin), db=Depends(get_db),
):
    try:
        return transfer_service.create_destination(
            db, admin["organization_id"], value.model_dump(),
        )
    except pymysql.IntegrityError as exc:
        raise HTTPException(409, "This transfer number is already configured") from exc


@router.patch("/destinations/{destination_id}", response_model=StaffDestinationResponse)
def update_destination(
    destination_id: int, value: StaffDestinationUpdate,
    admin=Depends(current_admin), db=Depends(get_db),
):
    try:
        destination = transfer_service.update_destination(
            db, admin["organization_id"], destination_id,
            value.model_dump(exclude_unset=True),
        )
    except pymysql.IntegrityError as exc:
        raise HTTPException(409, "This transfer number is already configured") from exc
    if not destination:
        raise HTTPException(404, "Transfer destination not found")
    return destination


@router.delete("/destinations/{destination_id}", status_code=204)
def delete_destination(
    destination_id: int, admin=Depends(current_admin), db=Depends(get_db),
):
    try:
        deleted = transfer_service.delete_destination(
            db, admin["organization_id"], destination_id,
        )
    except pymysql.IntegrityError as exc:
        raise HTTPException(
            409,
            "This destination is used by an IVR option or has transfer history; "
            "disable it instead of deleting.",
        ) from exc
    if not deleted:
        raise HTTPException(404, "Transfer destination not found")


@router.get("/calls/{call_log_id}", response_model=list[TransferResponse])
def call_transfers(call_log_id: int, admin=Depends(current_admin), db=Depends(get_db)):
    if not call_log_service.get_call_log_by_id(db, call_log_id, admin["organization_id"]):
        raise HTTPException(404, "Call log not found")
    return transfer_service.list_call_transfers(db, admin["organization_id"], call_log_id)


@router.post("/calls/{call_log_id}", response_model=TransferResponse, status_code=202)
def transfer_call(
    call_log_id: int,
    request: TransferRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    admin=Depends(current_admin),
    db=Depends(get_db),
):
    key = (idempotency_key or uuid.uuid4().hex).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", key):
        raise HTTPException(422, "Idempotency-Key must contain 8-128 safe characters")
    try:
        transfer = transfer_service.prepare_transfer(
            db,
            organization_id=admin["organization_id"],
            call_log_id=call_log_id,
            destination_id=request.destination_id,
            department=request.department,
            actor_user_id=admin["id"],
            idempotency_key=key,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    if transfer["status"] != "requested":
        return transfer
    base = (os.getenv("WEBHOOK_BASE_URL") or "").strip().rstrip("/")
    environment = (os.getenv("ENVIRONMENT") or "development").lower()
    if not base or (environment == "production" and not base.startswith("https://")):
        transfer_service.mark_failed(
            db, admin["organization_id"], transfer["id"],
            "A public HTTPS WEBHOOK_BASE_URL is required",
        )
        raise HTTPException(503, "Human transfer requires a public HTTPS webhook base URL")
    query = urlencode({
        "transfer_id": transfer["id"],
        "correlation_id": call_log_service.get_call_log_by_id(
            db, call_log_id, admin["organization_id"],
        )["correlation_id"],
    })
    answer_url = f"{base}/api/plivo/transfer-answer?{query}"
    callback_url = f"{base}/api/plivo/transfer-update-callback?{query}"
    try:
        provider = get_telephony_provider(db, admin["organization_id"])
        live = provider.get_call(transfer["provider_call_id"])
        if str(live.status or "").lower() not in transfer_service.LIVE_STATUSES:
            raise RuntimeError("Provider reports that the call is no longer live")
        provider.transfer_call(
            call_id=transfer["provider_call_id"], answer_url=answer_url,
            callback_url=callback_url,
        )
    except Exception as exc:
        transfer_service.mark_failed(
            db, admin["organization_id"], transfer["id"],
            f"{type(exc).__name__}: {str(exc)[:400]}",
        )
        raise HTTPException(502, "Plivo could not start the human transfer") from exc
    return transfer_service.set_provider_accepted(
        db, admin["organization_id"], transfer["id"],
    )
