from pydantic import BaseModel, Field

class LeadScoreRequest(BaseModel):
    interested: bool = Field(..., description="Whether the lead is interested in our services")
    budget: bool = Field(..., description="Whether the lead has budget budget to proceed")
    decision_maker: bool = Field(..., description="Whether the lead is a key decision maker")
    callback_requested: bool = Field(..., description="Whether a follow-up callback was requested")

class LeadScoreResponse(BaseModel):
    lead_score: int = Field(..., description="Calculated score (0 to 100)")
    status: str = Field(..., description="Status string (COLD_LEAD, WARM_LEAD, HOT_LEAD)")
    source: str = Field(default="manual_preview")
    persisted: bool = Field(default=False, description="Preview scores are never written to lead records")
