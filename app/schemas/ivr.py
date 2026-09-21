from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class IvrOptionInput(BaseModel):
    digit: str = Field(pattern=r"^[1-9]$")
    label: str = Field(min_length=1, max_length=80)
    campaign_id: Optional[int] = Field(default=None, ge=1)
    destination_id: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True
    sort_order: int = Field(default=100, ge=1, le=9999)

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def exactly_one_route(self):
        if bool(self.campaign_id) == bool(self.destination_id):
            raise ValueError(
                "Each IVR option must route to exactly one of campaign_id or destination_id"
            )
        return self


class IvrSettingsUpdate(BaseModel):
    is_active: bool = False
    timeout_seconds: int = Field(default=7, ge=3, le=15)
    prompt_english: str = Field(default="", max_length=500)
    prompt_tamil: str = Field(default="", max_length=500)
    options: list[IvrOptionInput] = Field(default_factory=list, max_length=9)

    @model_validator(mode="after")
    def validate_active_menu(self):
        if len({item.digit for item in self.options}) != len(self.options):
            raise ValueError("Each IVR option needs a unique digit")
        if self.is_active and not any(item.is_active for item in self.options):
            raise ValueError("An active IVR needs at least one active option")
        return self


class IvrOptionResponse(IvrOptionInput):
    id: int
    destination_name: Optional[str] = None
    destination_phone: Optional[str] = None


class IvrSettingsResponse(BaseModel):
    is_active: bool = False
    timeout_seconds: int = 7
    prompt_english: str = ""
    prompt_tamil: str = ""
    options: list[IvrOptionResponse] = Field(default_factory=list)
