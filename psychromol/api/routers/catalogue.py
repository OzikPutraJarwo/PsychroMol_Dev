from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ...rules import EQUIPMENT, EQUIPMENT_LABELS, METRICS, OPERATORS, SEVERITIES
from ..deps import RepositoryDep
from ..schemas import CropIn, FacilityIn
from .data import DEFAULT_DISPLAY_FIELDS, FIELDS

router = APIRouter(tags=["catalogue"])

@router.get("/meta")
def meta() -> dict[str, Any]:
    return {
        "metrics": [
            {"id": key, "label": value["label"], "unit": value["unit"]}
            for key, value in METRICS.items()
        ],
        "operators": list(OPERATORS),
        "severities": list(SEVERITIES),
        "equipment": [
            {"id": key, "label": EQUIPMENT_LABELS[key]} for key in EQUIPMENT
        ],
        "fields": [
            {"id": key, "label": label, "unit": unit}
            for key, (_column, unit, label) in FIELDS.items()
        ],
        "default_display_fields": list(DEFAULT_DISPLAY_FIELDS),
    }

@router.get("/crops")
def list_crops(repository: RepositoryDep) -> list[dict[str, Any]]:
    return [crop.to_dict() for crop in repository.list_crops()]

@router.post("/crops", status_code=status.HTTP_201_CREATED)
def create_crop(payload: CropIn, repository: RepositoryDep) -> dict[str, Any]:
    crop = repository.create_crop(
        name=payload.name,
        temperature_min=payload.temperature_min,
        temperature_max=payload.temperature_max,
        humidity_min=payload.humidity_min,
        humidity_max=payload.humidity_max,
        extra_targets=[item.model_dump() for item in payload.extra_targets],
    )
    return crop.to_dict()

@router.put("/crops/{crop_id}")
def update_crop(
    crop_id: int, payload: CropIn, repository: RepositoryDep
) -> dict[str, Any]:
    crop = repository.update_crop(
        crop_id,
        name=payload.name,
        temperature_min=payload.temperature_min,
        temperature_max=payload.temperature_max,
        humidity_min=payload.humidity_min,
        humidity_max=payload.humidity_max,
        extra_targets=[item.model_dump() for item in payload.extra_targets],
    )
    if crop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no crop {crop_id}")
    return crop.to_dict()

@router.delete("/crops/{crop_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_crop(crop_id: int, repository: RepositoryDep) -> None:
    used = repository.crop_in_use(crop_id)
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{used} profile(s) still use this crop",
        )
    if not repository.delete_crop(crop_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no crop {crop_id}")

@router.get("/facilities")
def list_facilities(repository: RepositoryDep) -> list[dict[str, Any]]:
    return [facility.to_dict() for facility in repository.list_facilities()]

def _clean_equipment(equipment: list[str]) -> list[str]:
    unknown = [item for item in equipment if item not in EQUIPMENT]
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"unknown equipment: {', '.join(unknown)}",
        )
    return [item for item in EQUIPMENT if item in set(equipment)]

@router.post("/facilities", status_code=status.HTTP_201_CREATED)
def create_facility(payload: FacilityIn, repository: RepositoryDep) -> dict[str, Any]:
    facility = repository.create_facility(
        name=payload.name,
        altitude_m=payload.altitude_m,
        equipment=_clean_equipment(payload.equipment),
    )
    return facility.to_dict()

@router.put("/facilities/{facility_id}")
def update_facility(
    facility_id: int, payload: FacilityIn, repository: RepositoryDep
) -> dict[str, Any]:
    facility = repository.update_facility(
        facility_id,
        name=payload.name,
        altitude_m=payload.altitude_m,
        equipment=_clean_equipment(payload.equipment),
    )
    if facility is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no facility {facility_id}")
    return facility.to_dict()

@router.delete("/facilities/{facility_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_facility(facility_id: int, repository: RepositoryDep) -> None:
    used = repository.facility_in_use(facility_id)
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{used} profile(s) still use this facility",
        )
    if not repository.delete_facility(facility_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no facility {facility_id}")
