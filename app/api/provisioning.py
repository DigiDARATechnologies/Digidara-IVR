"""Automated Plivo India number provisioning: KYC submission, approval status,
and number search/purchase for an organization's own dedicated Plivo identity.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.auth import current_admin
from app.database.db import get_db
from app.services import plivo_provisioning_service as provisioning

router = APIRouter(prefix="/provisioning/plivo", tags=["Provisioning"])


@router.get("/requirements")
def requirements(admin=Depends(current_admin)):
    try:
        return provisioning.get_compliance_requirements()
    except provisioning.ProvisioningError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/status")
def status(admin=Depends(current_admin), db=Depends(get_db)):
    application = provisioning.get_latest_application(db, admin["organization_id"])
    if not application:
        return {"status": "not_started"}
    return application


@router.post("/compliance")
async def submit_compliance(
    business_name: str = Form(...),
    business_email: str = Form(...),
    address_line1: str = Form(...),
    city: str = Form(...),
    state: str = Form(...),
    postal_code: str = Form(...),
    registration_number: str = Form(...),
    document_type_ids: str = Form(..., description="Comma-separated Plivo document_type_id values"),
    documents: list[UploadFile] = File(...),
    admin=Depends(current_admin),
    db=Depends(get_db),
):
    type_ids = [value.strip() for value in document_type_ids.split(",") if value.strip()]
    if len(type_ids) != len(documents):
        raise HTTPException(422, "document_type_ids count must match the number of uploaded files")

    base_url = (os.getenv("WEBHOOK_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        raise HTTPException(503, "WEBHOOK_BASE_URL is not configured; Plivo cannot call back with a decision")
    callback_url = f"{base_url}/api/plivo/compliance-webhook"

    saved_paths: list[str] = []
    try:
        for upload in documents:
            suffix = Path(upload.filename or "").suffix or ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(await upload.read())
                saved_paths.append(handle.name)

        try:
            return provisioning.submit_compliance_application(
                db, admin["organization_id"],
                business_name=business_name, business_email=business_email,
                address_line1=address_line1, city=city, state=state,
                postal_code=postal_code, registration_number=registration_number,
                document_type_ids=type_ids, document_paths=saved_paths,
                callback_url=callback_url,
            )
        except provisioning.ProvisioningError as exc:
            raise HTTPException(502, str(exc)) from exc
    finally:
        for path in saved_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


@router.get("/numbers")
def search_numbers(prefix: str, admin=Depends(current_admin)):
    try:
        return {"numbers": provisioning.search_numbers(prefix)}
    except provisioning.ProvisioningError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/numbers/buy")
def buy_number(
    number: str = Form(...),
    compliance_application_id: str = Form(...),
    admin=Depends(current_admin),
    db=Depends(get_db),
):
    try:
        return provisioning.provision_number(
            db, admin["organization_id"], number, compliance_application_id,
        )
    except provisioning.ProvisioningError as exc:
        raise HTTPException(502, str(exc)) from exc
