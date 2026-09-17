from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..ingest import Sample
from . import HardwareError
from .drivers import (
    MCP3008,
    Actuator,
    AnalogPercentSensor,
    AnalogSensor,
    Display,
    OledDisplay,
    SHT10Sensor,
    Stepper,
    Stepper28BYJ48,
    TemperatureHumiditySensor,
)
from .state import HardwareStateStore, store

logger = logging.getLogger(__name__)

def _pin(name: str, default: int) -> int:
    raw = os.environ.get(f"PSYCHROMOL_PIN_{name}")
    return int(raw) if raw else default

@dataclass
class HardwareRig:
    th_sensor: TemperatureHumiditySensor
    soil_sensor: AnalogSensor | None = None
    light_sensor: AnalogSensor | None = None
    display: Display | None = None
    actuators: dict[str, Actuator] = field(default_factory=dict)
    stepper: Stepper | None = None

def build_rig() -> HardwareRig:
    th_sensor = SHT10Sensor(
        sck_pin=_pin("SHT10_SCK", 23), data_pin=_pin("SHT10_DATA", 24)
    )

    soil_sensor: AnalogSensor | None = None
    light_sensor: AnalogSensor | None = None
    try:
        adc = MCP3008()
        soil_sensor = AnalogPercentSensor(adc, channel=0, invert=True)
        light_sensor = AnalogPercentSensor(adc, channel=1)
    except HardwareError:
        logger.warning("MCP3008 unavailable, soil moisture and light readings disabled")

    display: Display | None = None
    try:
        display = OledDisplay(address=_pin("OLED_ADDRESS", 0x3C))
    except HardwareError:
        logger.warning("OLED display unavailable")

    actuators: dict[str, Actuator] = {}
    from .drivers import GpioActuator

    for name, default_pin in (("fan", 17), ("pump", 27)):
        try:
            actuators[name] = GpioActuator(_pin(f"{name.upper()}_PIN", default_pin))
        except HardwareError:
            logger.warning("%s actuator unavailable", name)

    stepper: Stepper | None = None
    try:
        stepper = Stepper28BYJ48(
            (
                _pin("STEPPER_IN1", 5),
                _pin("STEPPER_IN2", 6),
                _pin("STEPPER_IN3", 13),
                _pin("STEPPER_IN4", 19),
            )
        )
    except HardwareError:
        logger.warning("stepper motor unavailable")

    return HardwareRig(
        th_sensor=th_sensor,
        soil_sensor=soil_sensor,
        light_sensor=light_sensor,
        display=display,
        actuators=actuators,
        stepper=stepper,
    )

def poll_once(
    rig: HardwareRig,
    pipeline,
    profile,
    state_store: HardwareStateStore = store,
) -> None:
    error: str | None = None
    try:
        temperature, humidity = rig.th_sensor.read()
        pipeline.store_samples(
            profile, [Sample(datetime.now(timezone.utc), temperature, humidity)]
        )
    except HardwareError as exc:
        error = str(exc)
        logger.warning("temperature/humidity read failed: %s", exc)

    soil = rig.soil_sensor.read_percent() if rig.soil_sensor else None
    light = rig.light_sensor.read_percent() if rig.light_sensor else None
    state_store.update_sensors(soil, light, error)

    if rig.display is not None:
        snapshot = state_store.snapshot()
        lines = ["PsychroMol"]
        if error is None:
            lines.append(f"T {temperature:.1f}C  RH {humidity:.0f}%")
        if soil is not None:
            lines.append(f"Soil {soil:.0f}%")
        if light is not None:
            lines.append(f"Light {light:.0f}%")
        for name, on in snapshot.actuators.items():
            lines.append(f"{name.capitalize()}: {'on' if on else 'off'}")
        rig.display.show(lines)

def set_actuator(rig: HardwareRig, name: str, on: bool, state_store: HardwareStateStore = store) -> None:
    actuator = rig.actuators.get(name)
    if actuator is None:
        raise HardwareError(f"no actuator named {name!r}")
    actuator.set(on)
    state_store.set_actuator(name, on)

def move_stepper(rig: HardwareRig, steps: int) -> None:
    if rig.stepper is None:
        raise HardwareError("no stepper motor configured")
    rig.stepper.move(steps)

_active_rig: HardwareRig | None = None

def set_active_rig(rig: HardwareRig | None) -> None:
    global _active_rig
    _active_rig = rig

def get_active_rig() -> HardwareRig | None:
    return _active_rig
