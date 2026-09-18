from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from ...fetcher import refresh
from ..deps import ProfileDep, RepositoryDep
from ..schemas import ProfileIn

router = APIRouter(prefix="/profiles", tags=["profiles"])

SOURCE_FIELDS = (
    "source_url", "field_time", "field_temperature", "field_humidity", "field_pressure",
    "pressure_mode", "pressure_unit",
)


@router.get("")
def list_profiles(repository: RepositoryDep) -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in repository.list_profiles()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(payload: ProfileIn, repository: RepositoryDep) -> dict[str, Any]:
    return repository.create_profile(**payload.model_dump()).to_dict()


@router.get("/{profile_id}")
def get_profile(profile: ProfileDep) -> dict[str, Any]:
    return profile.to_dict()


@router.put("/{profile_id}")
def update_profile(profile: ProfileDep, payload: ProfileIn, repository: RepositoryDep) -> dict[str, Any]:
    fields = payload.model_dump()
    if any(getattr(profile, name) != fields[name] for name in SOURCE_FIELDS):
        fields["last_polled_at"] = None
        fields["last_poll_error"] = None
    return repository.update_profile(profile, **fields).to_dict()


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile: ProfileDep, repository: RepositoryDep) -> None:
    repository.delete_profile(profile)


@router.post("/{profile_id}/refresh")
def refresh_profile(profile: ProfileDep, repository: RepositoryDep) -> dict[str, Any]:
    result = refresh(repository, profile)
    latest = repository.latest_reading(profile.id)
    return {
        "stored": result.stored,
        "error": result.error,
        "latest": latest.to_dict() if latest else None,
        "profile": profile.to_dict(),
    }
