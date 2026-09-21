from pydantic import BaseModel, Field
from typing import Optional

class CampaignBase(BaseModel):
    campaign_name: str = Field(..., min_length=1, max_length=255, description="Name of the campaign")
    objective: str = Field(..., min_length=1, description="Campaign objective details")
    ai_prompt: str = Field(..., min_length=1, description="Instructions/Prompt for the AI agent")

class CampaignCreate(CampaignBase):
    pass

class CampaignUpdate(BaseModel):
    campaign_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Name of the campaign")
    objective: Optional[str] = Field(None, min_length=1, description="Campaign objective details")
    ai_prompt: Optional[str] = Field(None, min_length=1, description="Instructions/Prompt for the AI agent")

class CampaignResponse(CampaignBase):
    id: int

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "campaign_name": "Summer Outbound Sales",
                "objective": "Follow up with interested leads from last month",
                "ai_prompt": "You are a friendly customer success manager calling to offering a discount..."
            }
        }