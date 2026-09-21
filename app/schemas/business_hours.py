import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class DaySchedule(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday .. 6=Sunday")
    is_closed: bool = False
    open_time: Optional[str] = Field(None, description="24-hour HH:MM, organization-local time")
    close_time: Optional[str] = Field(None, description="24-hour HH:MM, organization-local time")

    @field_validator("open_time", "close_time")
    @classmethod
    def _validate_time_format(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not _TIME_RE.match(value):
            raise ValueError("time must be in 24-hour HH:MM format, e.g. '09:30'")
        return value

    @model_validator(mode="after")
    def _validate_open_before_close(self) -> "DaySchedule":
        if not self.is_closed:
            if not self.open_time or not self.close_time:
                raise ValueError("open_time and close_time are required when is_closed is false")
            if self.open_time >= self.close_time:
                raise ValueError(
                    "open_time must be earlier than close_time "
                    "(schedules spanning midnight are not supported yet)"
                )
        return self


class BusinessHoursSet(BaseModel):
    timezone: str = Field(..., description="IANA timezone, e.g. 'Asia/Kolkata'")
    days: List[DaySchedule] = Field(..., description="Exactly one entry for each day, 0-6")

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError(f"unknown IANA timezone: {value!r}")
        return value

    @model_validator(mode="after")
    def _validate_all_days_present_once(self) -> "BusinessHoursSet":
        seen = [day.day_of_week for day in self.days]
        if sorted(seen) != list(range(7)):
            raise ValueError("days must include exactly one entry for each day 0-6")
        return self


class BusinessHoursResponse(BaseModel):
    organization_id: int
    timezone: str
    configured: bool = Field(
        ..., description="False if no schedule has been set yet (inbound calls are always accepted)."
    )
    days: List[DaySchedule]


class BusinessHoursStatus(BaseModel):
    is_open: bool
    configured: bool
    organization_timezone: str
    local_time: str
    day_of_week: int
