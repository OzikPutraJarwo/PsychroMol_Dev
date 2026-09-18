from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

DEFAULT_POLL_INTERVAL_SECONDS = 60


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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    crop_name: Mapped[str] = mapped_column(String(120), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)

    temperature_min: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_max: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_reference: Mapped[str] = mapped_column(Text, nullable=False)
    humidity_min: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_max: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_reference: Mapped[str] = mapped_column(Text, nullable=False)
    vpd_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    vpd_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    vpd_reference: Mapped[str | None] = mapped_column(Text, nullable=True)

    pressure_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="standard")
    pressure_kpa: Mapped[float | None] = mapped_column(Float, nullable=True)

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    poll_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_POLL_INTERVAL_SECONDS
    )
    field_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_temperature: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_humidity: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_pressure: Mapped[str | None] = mapped_column(Text, nullable=True)
    pressure_unit: Mapped[str] = mapped_column(String(5), nullable=False, default="kPa")

    rules_seeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_polled_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    last_poll_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "crop_name": self.crop_name,
            "stage": self.stage,
            "temperature_min": self.temperature_min,
            "temperature_max": self.temperature_max,
            "temperature_reference": self.temperature_reference,
            "humidity_min": self.humidity_min,
            "humidity_max": self.humidity_max,
            "humidity_reference": self.humidity_reference,
            "vpd_min": self.vpd_min,
            "vpd_max": self.vpd_max,
            "vpd_reference": self.vpd_reference,
            "pressure_mode": self.pressure_mode,
            "pressure_kpa": self.pressure_kpa,
            "source_url": self.source_url,
            "poll_interval_seconds": self.poll_interval_seconds,
            "field_time": self.field_time,
            "field_temperature": self.field_temperature,
            "field_humidity": self.field_humidity,
            "field_pressure": self.field_pressure,
            "pressure_unit": self.pressure_unit,
            "rules_seeded": self.rules_seeded,
            "last_polled_at": iso(self.last_polled_at),
            "last_poll_error": self.last_poll_error,
        }


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (UniqueConstraint("profile_id", "measured_at", name="uq_reading"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    measured_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    relative_humidity_percent: Mapped[float] = mapped_column(Float, nullable=False)
    pressure_kpa: Mapped[float | None] = mapped_column(Float, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "measured_at": iso(self.measured_at),
            "received_at": iso(self.received_at),
            "temperature_c": self.temperature_c,
            "relative_humidity_percent": self.relative_humidity_percent,
            "pressure_kpa": self.pressure_kpa,
        }


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    temperature: Mapped[str] = mapped_column(String(8), nullable=False, default="ANY")
    humidity: Mapped[str] = mapped_column(String(8), nullable=False, default="ANY")
    vpd: Mapped[str] = mapped_column(String(8), nullable=False, default="ANY")
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile_id": self.profile_id,
            "name": self.name,
            "conditions": {
                "temperature": self.temperature,
                "humidity": self.humidity,
                "vpd": self.vpd,
            },
            "severity": self.severity,
            "recommendation": self.recommendation,
            "reference": self.reference,
            "priority": self.priority,
            "enabled": self.enabled,
        }
