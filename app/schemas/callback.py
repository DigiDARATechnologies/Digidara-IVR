from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


CallbackStatus = Literal["pending", "assigned", "completed", "cancelled"]


class CallbackUpdate(BaseModel):
    status: Optional[CallbackStatus] = None
    assigned_user_id: Optional[int] = Field(default=None, ge=1)
    clear_assignee: bool = False
    requested_date: Optional[date] = None
    scheduled_at: Optional[datetime] = None
    clear_schedule: bool = False
    notes: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_clear_flags(self):
        if self.clear_assignee and self.assigned_user_id is not None:
            raise ValueError("assigned_user_id and clear_assignee cannot be used together")
        if self.clear_schedule and self.scheduled_at is not None:
            raise ValueError("scheduled_at and clear_schedule cannot be used together")
        return self


class CallbackResponse(BaseModel):
    id: int
    organization_id: int
    customer_id: int
    campaign_id: Optional[int] = None
    source_call_log_id: Optional[int] = None
    reminder_type: str
    source: str
    requested_date: Optional[date] = None
    scheduled_at: Optional[datetime] = None
    timezone: str
    status: CallbackStatus
    assigned_user_id: Optional[int] = None
    assigned_user_name: Optional[str] = None
    notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    completed_by_user_id: Optional[int] = None
    customer_name: str
    customer_phone: Optional[str] = None
    call_summary: Optional[str] = None
    lead_score: Optional[int] = None
    qualification: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CallbackSummary(BaseModel):
    pending: int = 0
    assigned: int = 0
    overdue: int = 0
    due_today: int = 0
    completed: int = 0

