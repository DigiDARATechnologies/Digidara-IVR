from pydantic import BaseModel, Field

class CallStartRequest(BaseModel):
    customer_id: int = Field(..., description="The ID of the customer to call")
    campaign_id: int = Field(..., description="The ID of the campaign to use")

class CallStartResponse(BaseModel):
    message: str = Field(..., description="Status/Success message")
    call_sid: str = Field(..., description="Backward-compatible provider call/request ID")
    provider: str = "plivo"
    provider_call_id: str | None = None
    request_id: str | None = None
    status: str = Field(..., description="The status of the call (e.g. initiated, failed)")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "message": "Call initiated successfully",
                "call_sid": "mock_call_sid_1717387349",
                "status": "initiated"
            }
        }

class SheetCallRequest(BaseModel):
    sheet_url: str = Field(..., description="Google Sheet link containing customer details")
    campaign_id: int = Field(..., description="Campaign ID to trigger calls for")
