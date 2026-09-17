from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

class Base(DeclarativeBase):
    pass

def _now() -> datetime:
    return datetime.now(timezone.utc)

class Crop(Base):
    __tablename__ = "crops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    temperature_min: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_max: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_min: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_max: Mapped[float] = mapped_column(Float, nullable=False)
    extra_targets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)

    profiles: Mapped[list[Profile]] = relationship(back_populates="crop")

    def targets(self) -> dict[str, dict[str, float | None]]:
        found: dict[str, dict[str, float | None]] = {
            "temperature": {"min": self.temperature_min, "max": self.temperature_max},
            "relative_humidity": {"min": self.humidity_min, "max": self.humidity_max},
        }
        for entry in self.extra_targets or []:
            metric = entry.get("metric")
            if metric:
                found[metric] = {"min": entry.get("min"), "max": entry.get("max")}
        return found

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "temperature_min": self.temperature_min,
            "temperature_max": self.temperature_max,
            "humidity_min": self.humidity_min,
            "humidity_max": self.humidity_max,
            "extra_targets": list(self.extra_targets or []),
            "targets": self.targets(),
        }

class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    altitude_m: Mapped[float] = mapped_column(Float, default=0.0)
    equipment: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)

    profiles: Mapped[list[Profile]] = relationship(back_populates="facility")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "altitude_m": self.altitude_m,
            "equipment": list(self.equipment or []),
        }

DEFAULT_POLL_INTERVAL_SECONDS = 60

class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    poll_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_poll_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)

    crop: Mapped[Crop] = relationship(back_populates="profiles", lazy="joined")
    facility: Mapped[Facility] = relationship(back_populates="profiles", lazy="joined")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "crop_id": self.crop_id,
            "facility_id": self.facility_id,
            "crop": self.crop.to_dict() if self.crop else None,
            "facility": self.facility.to_dict() if self.facility else None,
            "source_url": self.source_url,
            "source_note": self.source_note,
            "poll_interval_seconds": self.poll_interval_seconds or DEFAULT_POLL_INTERVAL_SECONDS,
            "last_polled_at": (
                self.last_polled_at.isoformat() if self.last_polled_at else None
            ),
            "last_poll_error": self.last_poll_error,
            "is_default": self.is_default,
        }

class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (UniqueConstraint("profile_id", "measured_at", name="uq_reading"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    measured_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True, nullable=False)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)

    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure: Mapped[float] = mapped_column(Float, nullable=False)

    saturation_vapour_pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    vapour_pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    dew_point: Mapped[float | None] = mapped_column(Float, nullable=True)
    wet_bulb: Mapped[float | None] = mapped_column(Float, nullable=True)
    enthalpy: Mapped[float | None] = mapped_column(Float, nullable=True)
    specific_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    density: Mapped[float | None] = mapped_column(Float, nullable=True)
    vpd: Mapped[float | None] = mapped_column(Float, nullable=True)
    absolute_humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    degree_of_saturation: Mapped[float | None] = mapped_column(Float, nullable=True)
    dew_point_depression: Mapped[float | None] = mapped_column(Float, nullable=True)
    mollier_ordinate: Mapped[float | None] = mapped_column(Float, nullable=True)

    engine_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def usable(self) -> bool:
        return self.error is None and self.humidity_ratio is not None

class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    requires_equipment: Mapped[str | None] = mapped_column(String(40), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "conditions": list(self.conditions or []),
            "severity": self.severity,
            "recommendation": self.recommendation,
            "requires_equipment": self.requires_equipment,
            "priority": self.priority,
            "enabled": self.enabled,
        }
