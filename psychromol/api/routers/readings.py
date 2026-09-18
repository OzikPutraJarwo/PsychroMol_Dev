from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Query

from ..deps import ProfileDep, RepositoryDep

router = APIRouter(prefix="/profiles/{profile_id}/readings", tags=["readings"])

MAX_PAGE = 10000


def _utc(moment: datetime | None) -> datetime | None:
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=timezone.utc)


@router.get("")
def list_readings(
    profile: ProfileDep,
    repository: RepositoryDep,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(100, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
    order: Literal["asc", "desc"] = "desc",
    max_points: int | None = Query(None, ge=2, le=MAX_PAGE),
) -> dict[str, Any]:
    start, end = _utc(start), _utc(end)
    total = repository.count_readings(profile.id, start, end)
    if max_points is not None:
        rows = repository.thinned_readings(profile.id, start, end, max_points)
    else:
        rows = repository.readings(profile.id, start, end, limit, offset, newest_first=order == "desc")
    return {"total": total, "items": [row.to_dict() for row in rows]}


@router.get("/latest")
def latest_reading(profile: ProfileDep, repository: RepositoryDep) -> dict[str, Any] | None:
    reading = repository.latest_reading(profile.id)
    return reading.to_dict() if reading else None
