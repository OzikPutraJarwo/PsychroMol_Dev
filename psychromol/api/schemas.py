from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TargetIn(BaseModel):
    metric: str
    min: float | None = None
    max: float | None = None

class CropIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    temperature_min: float
    temperature_max: float
    humidity_min: float = Field(ge=0, le=100)
    humidity_max: float = Field(ge=0, le=100)
    extra_targets: list[TargetIn] = Field(default_factory=list)

    @field_validator("temperature_max")
    @classmethod
    def _temperature_order(cls, value: float, info: Any) -> float:
        low = info.data.get("temperature_min")
        if low is not None and value <= low:
            raise ValueError("temperature_max must be above temperature_min")
        return value

    @field_validator("humidity_max")
    @classmethod
    def _humidity_order(cls, value: float, info: Any) -> float:
        low = info.data.get("humidity_min")
        if low is not None and value <= low:
            raise ValueError("humidity_max must be above humidity_min")
        return value

class FacilityIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    altitude_m: float = Field(default=0.0, ge=-500, le=6000)
    equipment: list[str] = Field(default_factory=list)

class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    crop_id: int
    facility_id: int
    source_url: str | None = None
    source_note: str | None = None
    poll_interval_seconds: int | None = Field(default=None, ge=1, le=3600)
    is_default: bool = False

    @field_validator("source_url")
    @classmethod
    def _url_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if not text.startswith(("http://", "https://")):
            raise ValueError("the data link must start with http:// or https://")
        return text

class ConditionIn(BaseModel):
    metric: str
    operator: str
    value: float | None = None
    target: str | None = None
    offset: float | None = None

class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    conditions: list[ConditionIn] = Field(min_length=1)
    severity: str = "warning"
    recommendation: str = ""
    requires_equipment: str | None = None
    priority: int = Field(default=50, ge=0, le=999)
    enabled: bool = True

class TextIn(BaseModel):
    text: str = Field(min_length=1)
    filename: str = ""
