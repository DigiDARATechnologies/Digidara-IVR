import os
import pymysql
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.database.db import get_db
from app.api.auth import current_admin
from app.schemas.campaign import CampaignCreate, CampaignUpdate, CampaignResponse
from app.services import campaign_service

router = APIRouter(dependencies=[Depends(current_admin)])

@router.post(
    "/campaigns", 
    response_model=CampaignResponse, 
    status_code=status.HTTP_201_CREATED,
    summary="Create a new campaign",
    description="Creates a new campaign detailing its name, objective, and instructions/prompt."
)
def create_campaign(
    campaign_in: CampaignCreate, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    try:
        return campaign_service.create_campaign(
            db, admin["organization_id"], campaign_in
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error creating campaign: {str(e)}"
        )

@router.get(
    "/campaigns", 
    response_model=List[CampaignResponse],
    summary="Retrieve all campaigns",
    description="Fetches a list of all active/configured campaigns."
)
def read_campaigns(
    skip: int = 0, 
    limit: int = 100, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    return campaign_service.get_all_campaigns(
        db, admin["organization_id"], skip=skip, limit=limit
    )

@router.get(
    "/campaigns/{id}", 
    response_model=CampaignResponse,
    summary="Retrieve a campaign by ID",
    description="Fetches details of a specific campaign using its unique ID."
)
def read_campaign(
    id: int, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    campaign = campaign_service.get_campaign_by_id(db, id, admin["organization_id"])
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign with ID {id} not found."
        )
    return campaign

@router.put(
    "/campaigns/{id}", 
    response_model=CampaignResponse,
    summary="Update an existing campaign",
    description="Modifies specified fields of a campaign by ID."
)
def update_campaign(
    id: int, 
    campaign_in: CampaignUpdate, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    # Check if target campaign exists
    campaign = campaign_service.get_campaign_by_id(db, id, admin["organization_id"])
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign with ID {id} not found."
        )

    try:
        updated = campaign_service.update_campaign(
            db, id, admin["organization_id"], campaign_in
        )

        # Invalidate ALL cached greeting audio/text for this campaign across every
        # customer it has been used with. Without this, editing a campaign's
        # ai_prompt would have no effect on calls until each individual
        # customer+campaign cache file happened to be cleared by other logic —
        # this guarantees the very next call for this campaign always reflects
        # the latest saved prompt.
        try:
            import glob
            audio_dir = os.path.join(os.getcwd(), "audio_cache")
            stale_pattern = os.path.join(audio_dir, f"first_greeting_*_{id}_*")
            for old_path in glob.glob(stale_pattern):
                try:
                    os.remove(old_path)
                except Exception:
                    pass
        except Exception as cache_err:
            print("Failed to clear greeting cache after campaign update:", cache_err)

        return updated
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error updating campaign: {str(e)}"
        )

@router.delete(
    "/campaigns/{id}",
    summary="Delete a campaign",
    description="Permanently deletes a campaign from the database."
)
def delete_campaign(
    id: int, 
    admin=Depends(current_admin),
    db: pymysql.Connection = Depends(get_db)
):
    success = campaign_service.delete_campaign(db, id, admin["organization_id"])
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Campaign with ID {id} not found."
        )
    return {"message": f"Campaign with ID {id} deleted successfully."}
