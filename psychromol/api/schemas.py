from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..fields import segments_of

Stage = Literal["propagation", "vegetative", "flowering"]
State = Literal["ANY", "LOW", "OPTIMAL", "HIGH"]
Severity = Literal["ok", "warning", "critical"]


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class ProfileIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    crop_name: str = Field(min_length=1, max_length=120)
    stage: Stage

    temperature_min: float = Field(ge=-100, le=200, allow_inf_nan=False)
    temperature_max: float = Field(ge=-100, le=200, allow_inf_nan=False)
    temperature_reference: str = Field(min_length=1)
    humidity_min: float = Field(ge=0, le=100, allow_inf_nan=False)
    humidity_max: float = Field(ge=0, le=100, allow_inf_nan=False)
    humidity_reference: str = Field(min_length=1)
    vpd_min: float | None = Field(default=None, ge=0, le=10, allow_inf_nan=False)
    vpd_max: float | None = Field(default=None, ge=0, le=10, allow_inf_nan=False)
    vpd_reference: str | None = None

    pressure_mode: Literal["standard", "fixed", "field"] = "standard"
    pressure_kpa: float | None = Field(default=None, ge=20, le=200, allow_inf_nan=False)

    source_url: str | None = Field(default=None, max_length=2000)
    poll_interval_seconds: int = Field(default=60, ge=1, le=86400)
    field_time: str | None = None
    field_temperature: str | None = None
    field_humidity: str | None = None
    field_pressure: str | None = None
    pressure_unit: Literal["kPa", "hPa", "Pa"] = "kPa"

    @field_validator(
        "vpd_reference", "source_url", "field_time", "field_temperature", "field_humidity",
        "field_pressure", mode="before",
    )
    @classmethod
    def blank_is_none(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("field_time", "field_temperature", "field_humidity", "field_pressure")
    @classmethod
    def is_pointer(cls, value: str | None) -> str | None:
        if value is not None:
            if not value.startswith("/"):
                raise ValueError(f"{value!r} is not a field path; it must start with /")
            segments_of(value)
        return value

    @field_validator("source_url")
    @classmethod
    def is_link(cls, value: str | None) -> str | None:
        if value is not None and not value.lower().startswith(("http://", "https://")):
            raise ValueError("the JSON link must start with http:// or https://")
        return value

    @model_validator(mode="after")
    def consistent(self) -> ProfileIn:
        if self.temperature_min >= self.temperature_max:
            raise ValueError("the temperature minimum must be below the maximum")
        if self.humidity_min >= self.humidity_max:
            raise ValueError("the humidity minimum must be below the maximum")
        custom = (self.vpd_min is not None, self.vpd_max is not None)
        if any(custom) and not all(custom):
            raise ValueError("a custom VPD band needs both a minimum and a maximum")
        if all(custom):
            if self.vpd_min >= self.vpd_max:
                raise ValueError("the VPD minimum must be below the maximum")
            if not self.vpd_reference:
                raise ValueError("a custom VPD band needs its reference")
        else:
            self.vpd_reference = None
        if self.pressure_mode == "fixed" and self.pressure_kpa is None:
            raise ValueError("a fixed pressure needs a value in kPa")
        if self.pressure_mode == "field" and not self.field_pressure:
            raise ValueError("pressure from the JSON link needs its field")
        if self.source_url and not (self.field_temperature and self.field_humidity):
            raise ValueError("choose the temperature and humidity fields for the JSON link")
        return self


class ConditionsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: State = "ANY"
    humidity: State = "ANY"
    vpd: State = "ANY"


class RuleIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    conditions: ConditionsIn = Field(default_factory=ConditionsIn)
    severity: Severity
    recommendation: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    priority: int
    enabled: bool = True
