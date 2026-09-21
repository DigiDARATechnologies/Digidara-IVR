from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import current_admin
from app.database.db import get_db
from app.schemas.callback import CallbackResponse, CallbackSummary, CallbackUpdate
from app.services import callback_service


router = APIRouter(prefix="/callbacks", tags=["Callbacks"], dependencies=[Depends(current_admin)])


@router.get("", response_model=list[CallbackResponse])
def read_callbacks(
    status: Optional[str] = None,
    assigned_user_id: Optional[int] = None,
    search: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    admin=Depends(current_admin),
    db=Depends(get_db),
):
    try:
        return callback_service.list_callbacks(
            db, admin["organization_id"], status=status,
            assigned_user_id=assigned_user_id, search=search, limit=limit, skip=skip,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/summary", response_model=CallbackSummary)
def read_callback_summary(admin=Depends(current_admin), db=Depends(get_db)):
    return callback_service.summary(db, admin["organization_id"])


@router.get("/{callback_id}", response_model=CallbackResponse)
def read_callback(callback_id: int, admin=Depends(current_admin), db=Depends(get_db)):
    callback = callback_service.get_by_id(db, admin["organization_id"], callback_id)
    if not callback:
        raise HTTPException(status_code=404, detail="Callback task not found")
    return callback


@router.patch("/{callback_id}", response_model=CallbackResponse)
def update_callback(
    callback_id: int,
    update: CallbackUpdate,
    admin=Depends(current_admin),
    db=Depends(get_db),
):
    try:
        callback = callback_service.update_callback(
            db,
            organization_id=admin["organization_id"],
            callback_id=callback_id,
            actor_user_id=admin["id"],
            changes=update.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not callback:
        raise HTTPException(status_code=404, detail="Callback task not found")
    return callback

