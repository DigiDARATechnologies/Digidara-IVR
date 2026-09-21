"""Typed contracts shared by the facility HTTP, MCP, and agent layers."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AssetStatus = Literal["operational", "degraded", "offline", "maintenance"]
AlertSeverity = Literal["critical", "high", "medium", "low"]
ServiceRequestStatus = Literal["open", "in_progress", "resolved", "cancelled"]
ActionConfirmationStatus = Literal["pending", "approved", "consumed", "expired", "rejected"]


class FacilitySiteOut(BaseModel):
    id: int
    name: str
    code: str
    timezone: str


class FacilityAssetOut(BaseModel):
    id: int
    site_id: int
    asset_code: str
    name: str
    asset_type: str
    status: AssetStatus
    location: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FacilitySensorReadingOut(BaseModel):
    id: int
    asset_id: int | None = None
    sensor_code: str
    metric: str
    value: float
    unit: str
    observed_at: datetime


class FacilityAlertOut(BaseModel):
    id: int
    site_id: int
    asset_id: int | None = None
    severity: AlertSeverity
    title: str
    message: str
    status: Literal["active", "acknowledged", "resolved"]
    opened_at: datetime


class FacilityServiceRequestOut(BaseModel):
    id: int
    site_id: int
    asset_id: int | None = None
    request_number: str
    title: str
    description: str
    priority: AlertSeverity
    status: ServiceRequestStatus
    created_at: datetime


class ServiceRequestDraftInput(BaseModel):
    site_code: str = Field(min_length=1, max_length=80)
    asset_code: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10, max_length=5000)
    priority: AlertSeverity = "medium"


class ActionConfirmationOut(BaseModel):
    id: str
    action_type: Literal["create_service_request"]
    status: ActionConfirmationStatus
    expires_at: datetime
    summary: str


class FacilityAgentQueryInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class FacilityAgentResponse(BaseModel):
    reply: str
    route: Literal["knowledge", "live_data", "diagnosis", "action", "general"]
    route_source: Literal["llm", "safe_fallback"]
    citations: list[dict[str, str]] = Field(default_factory=list)
    requires_confirmation: bool = False


class FacilityOverviewOut(BaseModel):
    sites: list[FacilitySiteOut]
    assets: list[FacilityAssetOut]
    active_alerts: list[FacilityAlertOut]
    latest_readings: list[FacilitySensorReadingOut]
    open_service_requests: list[FacilityServiceRequestOut]


class DemoFacilitySeedOut(BaseModel):
    site: FacilitySiteOut
    assets_created: int
    sensors_created: int
    alerts_created: int
    message: str
