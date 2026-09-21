import re

from pydantic import BaseModel, Field, field_validator
from typing import Optional


def _normalize_plivo_number(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        raise ValueError("plivo_number must contain at least one digit")
    return digits


class PhoneNumberBase(BaseModel):
    plivo_number: str = Field(
        ..., min_length=4, max_length=20,
        description="The Plivo DID, digits only (e.g. '918041234567').",
    )
    campaign_id: int = Field(
        ..., description="The campaign inbound calls to this number are routed through.",
    )
    label: Optional[str] = Field(None, max_length=120, description="Human-friendly name, e.g. 'Bangalore front desk'.")
    is_active: bool = Field(True, description="Inactive numbers reject inbound calls.")

    @field_validator("plivo_number")
    @classmethod
    def _validate_number(cls, value: str) -> str:
        return _normalize_plivo_number(value)


class PhoneNumberCreate(PhoneNumberBase):
    pass


class PhoneNumberUpdate(BaseModel):
    campaign_id: Optional[int] = None
    label: Optional[str] = Field(None, max_length=120)
    is_active: Optional[bool] = None


class PhoneNumberResponse(PhoneNumberBase):
    id: int
    organization_id: int
    created_at: str

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "organization_id": 1,
                "campaign_id": 3,
                "plivo_number": "918041234567",
                "label": "Bangalore front desk",
                "is_active": True,
                "created_at": "2026-09-15 00:00:00",
            }
        }
