from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import current_admin
from app.database.db import get_db
from app.schemas.ivr import IvrSettingsResponse, IvrSettingsUpdate
from app.services import ivr_service

router = APIRouter(prefix="/ivr", tags=["IVR"], dependencies=[Depends(current_admin)])


@router.get("/settings", response_model=IvrSettingsResponse)
def read_settings(admin=Depends(current_admin), db=Depends(get_db)):
    return ivr_service.get_settings(db, int(admin["organization_id"]))


@router.put("/settings", response_model=IvrSettingsResponse)
def save_settings(value: IvrSettingsUpdate, admin=Depends(current_admin), db=Depends(get_db)):
    try:
        return ivr_service.update_settings(db, int(admin["organization_id"]), value.model_dump(), int(admin["id"]))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
