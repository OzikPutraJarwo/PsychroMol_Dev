from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ...hardware import HardwareError
from ...hardware.runtime import get_active_rig, move_stepper, set_actuator
from ...hardware.state import store

router = APIRouter(prefix="/hardware", tags=["hardware"])

class ActuatorIn(BaseModel):
    on: bool

class StepperIn(BaseModel):
    steps: int

def _require_rig():
    rig = get_active_rig()
    if rig is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "hardware is not enabled on this server"
        )
    return rig

@router.get("/status")
def status_() -> dict[str, Any]:
    rig = get_active_rig()
    snapshot = store.snapshot().to_dict()
    snapshot["enabled"] = rig is not None
    snapshot["actuator_names"] = sorted(rig.actuators) if rig else []
    snapshot["stepper_available"] = bool(rig and rig.stepper is not None)
    return snapshot

@router.post("/actuators/{name}")
def set_actuator_state(name: str, payload: ActuatorIn) -> dict[str, Any]:
    rig = _require_rig()
    try:
        set_actuator(rig, name, payload.on)
    except HardwareError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"name": name, "on": payload.on}

@router.post("/stepper")
def move_stepper_endpoint(payload: StepperIn) -> dict[str, Any]:
    rig = _require_rig()
    try:
        move_stepper(rig, payload.steps)
    except HardwareError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"moved": payload.steps}
