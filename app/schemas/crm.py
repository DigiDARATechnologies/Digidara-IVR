from datetime import datetime
from typing import Any, Optional
import ipaddress
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class CrmConnectionInput(BaseModel):
    name: str = Field(default="DigiDARA CRM Webhook", min_length=2, max_length=120)
    webhook_url: str = Field(min_length=10, max_length=1000)
    signing_secret: str = Field(min_length=16, max_length=500)
    is_active: bool = True
    field_mapping: dict[str, str] = Field(default_factory=dict)

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("CRM webhook URL must be an absolute HTTPS URL")
        if parsed.username or parsed.password:
            raise ValueError("CRM webhook URL must not contain embedded credentials")
        if parsed.hostname.casefold() == "localhost":
            raise ValueError("CRM webhook URL must use a public host")
        try:
            address = ipaddress.ip_address(parsed.hostname)
            if not address.is_global:
                raise ValueError("CRM webhook URL must use a public host")
        except ValueError as exc:
            if "public host" in str(exc):
                raise
        return value.strip()


class CrmConnectionResponse(BaseModel):
    configured: bool
    id: Optional[int] = None
    provider: str = "webhook"
    name: Optional[str] = None
    endpoint_host: Optional[str] = None
    is_active: bool = False
    field_mapping: dict[str, str] = Field(default_factory=dict)
    last_tested_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    updated_at: Optional[datetime] = None


class CrmOutboxResponse(BaseModel):
    id: int
    event_type: str
    aggregate_type: str
    aggregate_id: str
    status: str
    attempts: int
    max_attempts: int
    available_at: datetime
    delivered_at: Optional[datetime] = None
    last_error: Optional[str] = None
    response_status: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class CrmDeliveryResult(BaseModel):
    status: str
    event_id: Optional[int] = None
    detail: Optional[str] = None
