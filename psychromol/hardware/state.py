from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class HardwareState:
    soil_moisture_percent: float | None = None
    light_percent: float | None = None
    actuators: dict[str, bool] = field(default_factory=dict)
    updated_at: datetime | None = None
    sensor_error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "soil_moisture_percent": self.soil_moisture_percent,
            "light_percent": self.light_percent,
            "actuators": dict(self.actuators),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "sensor_error": self.sensor_error,
        }

class HardwareStateStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = HardwareState()

    def snapshot(self) -> HardwareState:
        with self._lock:
            return HardwareState(**vars(self._state) | {"actuators": dict(self._state.actuators)})

    def update_sensors(
        self, soil_moisture_percent: float | None, light_percent: float | None, error: str | None
    ) -> None:
        with self._lock:
            self._state.soil_moisture_percent = soil_moisture_percent
            self._state.light_percent = light_percent
            self._state.sensor_error = error
            self._state.updated_at = datetime.now(timezone.utc)

    def set_actuator(self, name: str, on: bool) -> None:
        with self._lock:
            self._state.actuators[name] = on

store = HardwareStateStore()
