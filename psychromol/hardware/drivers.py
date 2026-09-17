from __future__ import annotations

import time
from typing import Protocol

from . import HardwareError


class TemperatureHumiditySensor(Protocol):
    def read(self) -> tuple[float, float]: ...

class AnalogSensor(Protocol):
    def read_percent(self) -> float: ...

class Display(Protocol):
    def show(self, lines: list[str]) -> None: ...

class Actuator(Protocol):
    def set(self, on: bool) -> None: ...
    @property
    def is_on(self) -> bool: ...

class Stepper(Protocol):
    def move(self, steps: int) -> None: ...

class SimulatedTHSensor:
    def __init__(self, temperature: float = 24.0, humidity: float = 60.0) -> None:
        self.temperature = temperature
        self.humidity = humidity

    def read(self) -> tuple[float, float]:
        return self.temperature, self.humidity

class SimulatedAnalogSensor:
    def __init__(self, value: float = 50.0) -> None:
        self.value = value

    def read_percent(self) -> float:
        return self.value

class SimulatedDisplay:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def show(self, lines: list[str]) -> None:
        self.lines = list(lines)

class SimulatedActuator:
    def __init__(self) -> None:
        self._on = False

    def set(self, on: bool) -> None:
        self._on = on

    @property
    def is_on(self) -> bool:
        return self._on

class SimulatedStepper:
    def __init__(self) -> None:
        self.position = 0

    def move(self, steps: int) -> None:
        self.position += steps

def _require_gpio():
    try:
        import RPi.GPIO as GPIO
    except ImportError as exc:
        raise HardwareError(
            "RPi.GPIO is not installed. Install it on the Raspberry Pi with "
            "`pip install -r requirements-pi.txt`."
        ) from exc
    return GPIO

class SHT10Sensor:
    _TEMPERATURE = 0b00000011
    _HUMIDITY = 0b00000101

    def __init__(self, sck_pin: int, data_pin: int) -> None:
        self._gpio = _require_gpio()
        self.sck_pin = sck_pin
        self.data_pin = data_pin
        self._gpio.setup(self.sck_pin, self._gpio.OUT)
        self._gpio.setup(self.data_pin, self._gpio.OUT)

    def _set_data(self, direction) -> None:
        self._gpio.setup(self.data_pin, direction)

    def _clock_pulse(self, value: int | None = None) -> int:
        if value is not None:
            self._gpio.output(self.data_pin, value)
        self._gpio.output(self.sck_pin, self._gpio.HIGH)
        time.sleep(0.00001)
        bit = self._gpio.input(self.data_pin)
        self._gpio.output(self.sck_pin, self._gpio.LOW)
        return bit

    def _transmission_start(self) -> None:
        self._set_data(self._gpio.OUT)
        self._gpio.output(self.data_pin, self._gpio.HIGH)
        self._gpio.output(self.sck_pin, self._gpio.LOW)
        self._gpio.output(self.sck_pin, self._gpio.HIGH)
        self._gpio.output(self.data_pin, self._gpio.LOW)
        self._gpio.output(self.sck_pin, self._gpio.LOW)
        self._gpio.output(self.sck_pin, self._gpio.HIGH)
        self._gpio.output(self.data_pin, self._gpio.HIGH)
        self._gpio.output(self.sck_pin, self._gpio.LOW)

    def _send_command(self, command: int) -> None:
        self._set_data(self._gpio.OUT)
        for index in range(8):
            self._gpio.output(self.data_pin, (command >> (7 - index)) & 1)
            self._gpio.output(self.sck_pin, self._gpio.HIGH)
            self._gpio.output(self.sck_pin, self._gpio.LOW)
        self._set_data(self._gpio.IN)
        self._gpio.output(self.sck_pin, self._gpio.HIGH)
        ack = self._gpio.input(self.data_pin)
        self._gpio.output(self.sck_pin, self._gpio.LOW)
        if ack != 0:
            raise HardwareError("SHT10 did not acknowledge the command")

    def _read_raw(self, command: int) -> int:
        self._transmission_start()
        self._send_command(command)
        self._set_data(self._gpio.IN)
        deadline = time.monotonic() + 0.5
        while self._gpio.input(self.data_pin) == self._gpio.HIGH:
            if time.monotonic() > deadline:
                raise HardwareError("SHT10 measurement timed out")
            time.sleep(0.001)
        value = 0
        for _ in range(16):
            value = (value << 1) | self._clock_pulse()
        self._set_data(self._gpio.OUT)
        self._gpio.output(self.data_pin, self._gpio.HIGH)
        self._gpio.output(self.sck_pin, self._gpio.HIGH)
        self._gpio.output(self.sck_pin, self._gpio.LOW)
        return value

    def read(self) -> tuple[float, float]:
        raw_temperature = self._read_raw(self._TEMPERATURE)
        raw_humidity = self._read_raw(self._HUMIDITY)
        temperature = -40.1 + 0.01 * raw_temperature
        linear_rh = -2.0468 + 0.0367 * raw_humidity - 1.5955e-6 * raw_humidity**2
        true_rh = (temperature - 25.0) * (0.01 + 0.00008 * raw_humidity) + linear_rh
        return temperature, max(0.0, min(100.0, true_rh))

class MCP3008:
    def __init__(self, bus: int = 0, device: int = 0) -> None:
        try:
            import spidev
        except ImportError as exc:
            raise HardwareError(
                "spidev is not installed. Install it on the Raspberry Pi with "
                "`pip install -r requirements-pi.txt` and enable SPI with raspi-config."
            ) from exc
        self._spi = spidev.SpiDev()
        self._spi.open(bus, device)
        self._spi.max_speed_hz = 1_350_000

    def read_channel(self, channel: int) -> int:
        if not 0 <= channel <= 7:
            raise HardwareError(f"MCP3008 channel must be 0-7, got {channel}")
        reply = self._spi.xfer2([1, (8 + channel) << 4, 0])
        return ((reply[1] & 3) << 8) + reply[2]

class AnalogPercentSensor:
    def __init__(
        self,
        adc: MCP3008,
        channel: int,
        low_raw: int = 0,
        high_raw: int = 1023,
        invert: bool = False,
    ) -> None:
        self.adc = adc
        self.channel = channel
        self.low_raw = low_raw
        self.high_raw = high_raw
        self.invert = invert

    def read_percent(self) -> float:
        raw = self.adc.read_channel(self.channel)
        span = self.high_raw - self.low_raw or 1
        percent = (raw - self.low_raw) / span * 100.0
        if self.invert:
            percent = 100.0 - percent
        return max(0.0, min(100.0, percent))

class OledDisplay:
    def __init__(self, address: int = 0x3C, port: int = 1) -> None:
        try:
            from luma.core.interface.serial import i2c
            from luma.core.render import canvas
            from luma.oled.device import ssd1306
        except ImportError as exc:
            raise HardwareError(
                "luma.oled is not installed. Install it on the Raspberry Pi with "
                "`pip install -r requirements-pi.txt`."
            ) from exc
        self._canvas = canvas
        self._device = ssd1306(i2c(port=port, address=address))

    def show(self, lines: list[str]) -> None:
        with self._canvas(self._device) as draw:
            for index, line in enumerate(lines[:6]):
                draw.text((0, index * 11), line, fill="white")

class GpioActuator:
    def __init__(self, pin: int, active_high: bool = True) -> None:
        self._gpio = _require_gpio()
        self.pin = pin
        self.active_high = active_high
        self._gpio.setup(self.pin, self._gpio.OUT)
        self._on = False
        self.set(False)

    def set(self, on: bool) -> None:
        level = on if self.active_high else not on
        self._gpio.output(self.pin, self._gpio.HIGH if level else self._gpio.LOW)
        self._on = on

    @property
    def is_on(self) -> bool:
        return self._on

_HALF_STEP_SEQUENCE = (
    (1, 0, 0, 0),
    (1, 1, 0, 0),
    (0, 1, 0, 0),
    (0, 1, 1, 0),
    (0, 0, 1, 0),
    (0, 0, 1, 1),
    (0, 0, 0, 1),
    (1, 0, 0, 1),
)

class Stepper28BYJ48:
    def __init__(self, pins: tuple[int, int, int, int], step_delay: float = 0.002) -> None:
        self._gpio = _require_gpio()
        self.pins = pins
        self.step_delay = step_delay
        for pin in pins:
            self._gpio.setup(pin, self._gpio.OUT)
            self._gpio.output(pin, self._gpio.LOW)
        self._phase = 0

    def move(self, steps: int) -> None:
        direction = 1 if steps >= 0 else -1
        for _ in range(abs(steps)):
            self._phase = (self._phase + direction) % len(_HALF_STEP_SEQUENCE)
            pattern = _HALF_STEP_SEQUENCE[self._phase]
            for pin, level in zip(self.pins, pattern, strict=True):
                self._gpio.output(pin, level)
            time.sleep(self.step_delay)
