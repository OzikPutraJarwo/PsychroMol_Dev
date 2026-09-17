from __future__ import annotations

import pytest

from psychromol.hardware import HardwareError
from psychromol.hardware.drivers import (
    SimulatedActuator,
    SimulatedAnalogSensor,
    SimulatedDisplay,
    SimulatedStepper,
    SimulatedTHSensor,
)
from psychromol.hardware.runtime import HardwareRig, move_stepper, poll_once, set_actuator
from psychromol.hardware.state import HardwareStateStore


@pytest.fixture
def rig():
    return HardwareRig(
        th_sensor=SimulatedTHSensor(temperature=23.4, humidity=61.0),
        soil_sensor=SimulatedAnalogSensor(value=42.0),
        light_sensor=SimulatedAnalogSensor(value=77.0),
        display=SimulatedDisplay(),
        actuators={"fan": SimulatedActuator(), "pump": SimulatedActuator()},
        stepper=SimulatedStepper(),
    )

def test_state_store_snapshot_is_isolated_from_later_updates():
    store = HardwareStateStore()
    store.update_sensors(50.0, 60.0, None)
    snapshot = store.snapshot()
    store.set_actuator("fan", True)
    assert snapshot.actuators == {}
    assert store.snapshot().actuators == {"fan": True}

def test_poll_once_stores_a_reading_and_updates_sensor_state(rig, pipeline, profile, repository):
    store = HardwareStateStore()
    poll_once(rig, pipeline, profile, state_store=store)

    reading = repository.latest_reading(profile.id)
    assert reading is not None
    assert reading.temperature == 23.4
    assert reading.relative_humidity == 61.0

    snapshot = store.snapshot()
    assert snapshot.soil_moisture_percent == 42.0
    assert snapshot.light_percent == 77.0
    assert snapshot.sensor_error is None
    assert rig.display.lines

def test_set_actuator_toggles_the_driver_and_the_state(rig):
    store = HardwareStateStore()
    set_actuator(rig, "fan", True, state_store=store)
    assert rig.actuators["fan"].is_on is True
    assert store.snapshot().actuators == {"fan": True}

def test_set_actuator_rejects_an_unknown_name(rig):
    with pytest.raises(HardwareError):
        set_actuator(rig, "heater", True)

def test_move_stepper_advances_position(rig):
    move_stepper(rig, 5)
    assert rig.stepper.position == 5

def test_move_stepper_without_one_configured_raises():
    rig = HardwareRig(th_sensor=SimulatedTHSensor())
    with pytest.raises(HardwareError):
        move_stepper(rig, 1)

def test_hardware_status_reports_disabled_by_default(client):
    response = client.get("/api/v1/hardware/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["actuator_names"] == []

def test_hardware_actuator_endpoint_refuses_when_disabled(client):
    response = client.post("/api/v1/hardware/actuators/fan", json={"on": True})
    assert response.status_code == 409

def test_hardware_actuator_endpoint_toggles_an_active_rig(client, rig):
    from psychromol.hardware.runtime import set_active_rig

    set_active_rig(rig)
    try:
        response = client.post("/api/v1/hardware/actuators/fan", json={"on": True})
        assert response.status_code == 200
        assert rig.actuators["fan"].is_on is True

        status_response = client.get("/api/v1/hardware/status")
        body = status_response.json()
        assert body["enabled"] is True
        assert "fan" in body["actuator_names"]
    finally:
        set_active_rig(None)

def test_hardware_actuator_endpoint_rejects_an_unknown_actuator(client, rig):
    from psychromol.hardware.runtime import set_active_rig

    set_active_rig(rig)
    try:
        response = client.post("/api/v1/hardware/actuators/heater", json={"on": True})
        assert response.status_code == 404
    finally:
        set_active_rig(None)
