from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ...core.chart import build_mollier_chart, build_psychrometric_chart
from ...pipeline import pressure_for
from ..deps import PipelineDep, RepositoryDep
from ..schemas import ProfileIn

router = APIRouter(prefix="/profiles", tags=["profiles"])

CHART_T_MIN = -20.0
CHART_T_MAX = 50.0
CHART_W_MAX = 0.050

def _require(repository: RepositoryDep, profile_id: int):
    profile = repository.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")
    return profile

@router.get("")
def list_profiles(repository: RepositoryDep) -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in repository.list_profiles()]

@router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileIn, repository: RepositoryDep) -> dict[str, Any]:
    if repository.get_crop(payload.crop_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"no crop {payload.crop_id}"
        )
    if repository.get_facility(payload.facility_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"no facility {payload.facility_id}"
        )
    profile = repository.create_profile(
        name=payload.name,
        crop_id=payload.crop_id,
        facility_id=payload.facility_id,
        source_url=payload.source_url,
        source_note=payload.source_note,
        poll_interval_seconds=payload.poll_interval_seconds,
        is_default=payload.is_default,
    )
    return profile.to_dict()

@router.put("/{profile_id}")
def update_profile(
    profile_id: int, payload: ProfileIn, repository: RepositoryDep
) -> dict[str, Any]:
    _require(repository, profile_id)
    if repository.get_crop(payload.crop_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"no crop {payload.crop_id}"
        )
    if repository.get_facility(payload.facility_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"no facility {payload.facility_id}"
        )
    profile = repository.update_profile(
        profile_id,
        name=payload.name,
        crop_id=payload.crop_id,
        facility_id=payload.facility_id,
        source_url=payload.source_url,
        source_note=payload.source_note,
        poll_interval_seconds=payload.poll_interval_seconds,
        is_default=payload.is_default,
    )
    return profile.to_dict()

@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: int, repository: RepositoryDep) -> None:
    if not repository.delete_profile(profile_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no profile {profile_id}")

@router.get("/{profile_id}/current")
def current(
    profile_id: int, repository: RepositoryDep, pipeline: PipelineDep
) -> dict[str, Any]:
    profile = _require(repository, profile_id)
    payload = pipeline.assess(profile)
    if payload is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no readings yet for this profile"
        )
    payload["profile"] = profile.to_dict()
    return payload

@router.get("/{profile_id}/chart")
def chart(
    profile_id: int,
    repository: RepositoryDep,
    kind: str = "psychrometric",
) -> dict[str, Any]:
    profile = _require(repository, profile_id)
    pressure = pressure_for(profile)
    target = (
        (
            profile.crop.temperature_min,
            profile.crop.temperature_max,
            profile.crop.humidity_min,
            profile.crop.humidity_max,
        )
        if profile.crop is not None
        else None
    )
    if kind == "mollier":
        geometry = build_mollier_chart(
            t_min=CHART_T_MIN, t_max=CHART_T_MAX, w_max=CHART_W_MAX, pressure=pressure,
            target=target,
        )
    elif kind == "psychrometric":
        geometry = build_psychrometric_chart(
            t_min=CHART_T_MIN, t_max=CHART_T_MAX, w_max=CHART_W_MAX, pressure=pressure,
            target=target,
        )
    else:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "kind must be psychrometric or mollier",
        )
    payload = geometry.to_dict()
    payload["kind"] = kind
    payload["pressure_kpa"] = round(pressure / 1000.0, 5)
    return payload
