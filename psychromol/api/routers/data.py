from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from ...pipeline import SourceError
from ..deps import PipelineDep, RepositoryDep
from ..schemas import TextIn

router = APIRouter(prefix="/profiles", tags=["data"])

MAX_UPLOAD = 16 * 1024 * 1024

FIELDS: dict[str, tuple[str, str, str]] = {
    "temperature": ("temperature_c", "°C", "Temperature"),
    "relative_humidity": ("relative_humidity_percent", "%", "Relative humidity"),
    "vpd": ("vpd_kpa", "kPa", "VPD"),
    "dew_point": ("dew_point_c", "°C", "Dew point"),
    "dew_point_depression": ("dew_point_depression_k", "K", "Dew point margin"),
    "wet_bulb": ("wet_bulb_c", "°C", "Wet bulb"),
    "humidity_ratio": ("humidity_ratio_g_kg", "g/kg", "Humidity ratio"),
    "enthalpy": ("enthalpy_kj_kg", "kJ/kg", "Enthalpy"),
    "absolute_humidity": ("absolute_humidity_g_m3", "g/m³", "Absolute humidity"),
    "specific_volume": ("specific_volume_m3_kg", "m³/kg", "Specific volume"),
    "density": ("density_kg_m3", "kg/m³", "Density"),
    "degree_of_saturation": ("degree_of_saturation_percent", "%", "Degree of saturation"),
    "vapour_pressure": ("vapour_pressure_kpa", "kPa", "Vapour pressure"),
    "saturation_vapour_pressure": ("saturation_vapour_pressure_kpa", "kPa", "Saturation pressure"),
    "pressure": ("pressure_kpa", "kPa", "Atmospheric pressure"),
    "mollier_ordinate": ("mollier_ordinate_kj_kg", "kJ/kg", "Mollier ordinate"),
}

DEFAULT_DISPLAY_FIELDS = ["temperature", "relative_humidity"]

def _require(repository: RepositoryDep, profile_id: int):
    profile = repository.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")
    return profile

def _value(reading: Any, field: str) -> float | None:
    if field == "vapour_pressure":
        raw = reading.vapour_pressure
        return None if raw is None else raw / 1000.0
    if field == "saturation_vapour_pressure":
        raw = reading.saturation_vapour_pressure
        return None if raw is None else raw / 1000.0
    if field == "pressure":
        return None if reading.pressure is None else reading.pressure / 1000.0
    if field == "humidity_ratio":
        raw = reading.humidity_ratio
        return None if raw is None else raw * 1000.0
    return getattr(reading, field, None)

def _row(reading: Any, fields: list[str]) -> dict[str, Any]:
    row: dict[str, Any] = {"measured_at": reading.measured_at.isoformat()}
    for field in fields:
        key = FIELDS[field][0]
        value = _value(reading, field)
        row[key] = None if value is None else round(value, 5)
    return row

def _window(
    hours: float | None, start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime]:
    if start is not None and end is not None:
        return start, end
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=hours or 24.0), now

@router.get("/{profile_id}/readings")
def readings(
    profile_id: int,
    repository: RepositoryDep,
    hours: float | None = Query(default=24.0, gt=0, le=8784),
    start: datetime | None = None,
    end: datetime | None = None,
    fields: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    _require(repository, profile_id)
    chosen = [name for name in (fields or list(FIELDS)) if name in FIELDS]
    if not chosen:
        chosen = list(FIELDS)
    begin, finish = _window(hours, start, end)
    rows = repository.readings_between(profile_id, begin, finish)
    return {
        "start": begin.isoformat(),
        "end": finish.isoformat(),
        "count": len(rows),
        "fields": [
            {"id": name, "key": FIELDS[name][0], "unit": FIELDS[name][1]}
            for name in chosen
        ],
        "readings": [_row(row, chosen) for row in rows if row.usable],
    }

@router.get("/{profile_id}/export")
def export(
    profile_id: int,
    repository: RepositoryDep,
    fmt: str = Query(default="csv", alias="format"),
    hours: float | None = Query(default=24.0, gt=0, le=8784),
    start: datetime | None = None,
    end: datetime | None = None,
    fields: Annotated[list[str] | None, Query()] = None,
) -> Response:
    profile = _require(repository, profile_id)
    chosen = [name for name in (fields or list(FIELDS)) if name in FIELDS]
    if not chosen:
        chosen = list(FIELDS)
    begin, finish = _window(hours, start, end)
    rows = [
        _row(row, chosen)
        for row in repository.readings_between(profile_id, begin, finish)
        if row.usable
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    safe = re.sub(r"[^a-z0-9]+", "-", profile.name.lower()).strip("-") or "readings"
    base = f"{safe}-{stamp}"

    if fmt == "json":
        body = json.dumps(
            {
                "profile": profile.name,
                "start": begin.isoformat(),
                "end": finish.isoformat(),
                "readings": rows,
            },
            indent=2,
        )
        return Response(
            body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{base}.json"'},
        )
    if fmt != "csv":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "format must be csv or json"
        )

    buffer = io.StringIO()
    header = ["measured_at"] + [FIELDS[name][0] for name in chosen]
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{base}.csv"'},
    )

@router.post("/{profile_id}/refresh")
def refresh(
    profile_id: int, repository: RepositoryDep, pipeline: PipelineDep
) -> dict[str, Any]:
    profile = _require(repository, profile_id)
    try:
        result = pipeline.refresh(profile)
    except SourceError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return result.to_dict()

@router.post("/{profile_id}/upload")
async def upload(
    profile_id: int,
    repository: RepositoryDep,
    pipeline: PipelineDep,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    profile = _require(repository, profile_id)
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "the file is larger than 16 MB"
        )
    try:
        result = pipeline.load_text(
            profile, raw.decode("utf-8", errors="replace"), file.filename or ""
        )
    except SourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return result.to_dict()

@router.post("/{profile_id}/paste")
def paste(
    profile_id: int,
    payload: TextIn,
    repository: RepositoryDep,
    pipeline: PipelineDep,
) -> dict[str, Any]:
    profile = _require(repository, profile_id)
    try:
        result = pipeline.load_text(profile, payload.text, payload.filename)
    except SourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return result.to_dict()
