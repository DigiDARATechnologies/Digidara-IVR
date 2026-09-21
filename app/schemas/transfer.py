from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


TransferStatus = Literal[
    "requested", "provider_accepted", "ringing", "answered",
    "completed", "failed", "cancelled",
]


def _e164(value: str) -> str:
    value = value.strip()
    if not value.startswith("+") or not value[1:].isdigit() or not 8 <= len(value[1:]) <= 15:
        raise ValueError("phone_e164 must be an E.164 number such as +919876543210")
    return value


class StaffDestinationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone_e164: str = Field(min_length=9, max_length=16)
    department: Optional[str] = Field(default=None, max_length=80)
    priority: int = Field(default=100, ge=1, le=9999)
    is_active: bool = True

    @field_validator("phone_e164")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return _e164(value)


class StaffDestinationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    phone_e164: Optional[str] = Field(default=None, min_length=9, max_length=16)
    department: Optional[str] = Field(default=None, max_length=80)
    priority: Optional[int] = Field(default=None, ge=1, le=9999)
    is_active: Optional[bool] = None

    @field_validator("phone_e164")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return _e164(value) if value is not None else None


class StaffDestinationResponse(BaseModel):
    id: int
    organization_id: int
    name: str
    phone_e164: str
    department: Optional[str] = None
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


class DepartmentResponse(BaseModel):
    id: int
    organization_id: int
    name: str
    description: Optional[str] = None
    is_active: bool
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class TransferRequest(BaseModel):
    destination_id: Optional[int] = Field(default=None, ge=1)
    department: Optional[str] = Field(default=None, max_length=80)


class TransferResponse(BaseModel):
    id: int
    organization_id: int
    call_log_id: int
    destination_id: int
    destination_name: Optional[str] = None
    destination_phone: Optional[str] = None
    department: Optional[str] = None
    status: TransferStatus
    provider_call_id: str
    provider_bleg_id: Optional[str] = None
    initiated_by_user_id: int
    failure_reason: Optional[str] = None
    requested_at: datetime
    answered_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime
