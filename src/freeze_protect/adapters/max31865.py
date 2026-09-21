from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from importlib import import_module
from math import isfinite, sqrt
from time import sleep
from typing import Any, Protocol

from freeze_protect.domain.models import SensorHealth, TemperatureReading

_CONFIG_WRITE = 0x80
_RTD_READ = 0x01
_FAULT_READ = 0x07

_CONFIG_3WIRE_50HZ = 0x11
_CONFIG_FAULT_CLEAR = 0x02
_CONFIG_BIAS = 0x80
_CONFIG_ONE_SHOT = 0x20

_BIAS_SETTLE_S = 0.010
_CONVERSION_50HZ_S = 0.066

_PT100_R0_OHM = 100.0
_REFERENCE_RESISTOR_OHM = 430.0
_CVD_A = 3.9083e-3
_CVD_B = -5.775e-7
_CVD_C = -4.183e-12

_FAULT_FLAGS: tuple[tuple[int, str], ...] = (
    (0x80, "RTD_HIGH_THRESHOLD"),
    (0x40, "RTD_LOW_THRESHOLD"),
    (0x20, "REFIN_HIGH"),
    (0x10, "REFIN_LOW"),
    (0x08, "RTDIN_LOW"),
    (0x04, "OVER_UNDERVOLTAGE"),
)


class SpiDevice(Protocol):
    def open(self) -> None: ...

    def transfer(self, payload: list[int]) -> list[int]: ...

    def close(self) -> None: ...


class LinuxSpiDevice:
    """Small py-spidev boundary opened only for one complete sensor sample."""

    def __init__(
        self,
        *,
        device_path: str = "/dev/spidev0.0",
        max_speed_hz: int = 500_000,
        mode: int = 1,
    ) -> None:
        self._device_path = device_path
        self._max_speed_hz = max_speed_hz
        self._mode = mode
        self._device: Any | None = None

    def open(self) -> None:
        try:
            spidev = import_module("spidev")
        except ImportError as error:
            raise OSError("spidev is not installed") from error
        device = spidev.SpiDev()
        self._device = device
        try:
            device.open_path(self._device_path)
            device.max_speed_hz = self._max_speed_hz
            device.mode = self._mode
            device.bits_per_word = 8
        except BaseException:
            self.close()
            raise

    def transfer(self, payload: list[int]) -> list[int]:
        if self._device is None:
            raise OSError("SPI device is not open")
        return list(self._device.xfer2(payload))

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            finally:
                self._device = None


class Max31865TemperatureSource:
    def __init__(
        self,
        *,
        spi_factory: Callable[[], SpiDevice] = LinuxSpiDevice,
        clock: Callable[[], datetime],
        sleeper: Callable[[float], None] = sleep,
        minimum_temperature_c: float = -50.0,
        maximum_temperature_c: float = 120.0,
    ) -> None:
        self._spi_factory = spi_factory
        self._clock = clock
        self._sleeper = sleeper
        self._minimum_temperature_c = minimum_temperature_c
        self._maximum_temperature_c = maximum_temperature_c
        self.last_fault_register: int | None = None
        self.last_faults: tuple[str, ...] = ()
        self.last_error: str | None = None

    def read(self) -> TemperatureReading:
        self.last_fault_register = None
        self.last_faults = ()
        self.last_error = None
        try:
            temperature_c = self._sample()
        except OSError:
            self.last_error = "spi_error"
            return TemperatureReading(None, self._clock(), SensorHealth.STALE)
        except (ArithmeticError, ValueError):
            self.last_error = "invalid_measurement"
            return TemperatureReading(None, self._clock(), SensorHealth.INVALID)
        return TemperatureReading(
            temperature_c,
            self._clock(),
            SensorHealth.HEALTHY,
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "source": "MAX31865_PT100",
            "device": "/dev/spidev0.0",
            "wiring": "3-wire",
            "reference_resistor_ohm": _REFERENCE_RESISTOR_OHM,
            "fault_register": self.last_fault_register,
            "faults": list(self.last_faults),
            "last_error": self.last_error,
        }

    def _sample(self) -> float:
        spi = self._spi_factory()
        opened = False
        try:
            spi.open()
            opened = True
            _write_config(spi, _CONFIG_3WIRE_50HZ | _CONFIG_FAULT_CLEAR)
            _write_config(spi, _CONFIG_3WIRE_50HZ | _CONFIG_BIAS)
            self._sleeper(_BIAS_SETTLE_S)
            _write_config(
                spi,
                _CONFIG_3WIRE_50HZ | _CONFIG_BIAS | _CONFIG_ONE_SHOT,
            )
            self._sleeper(_CONVERSION_50HZ_S)
            response = _transfer_exact(spi, [_RTD_READ, 0x00, 0x00], 3)
            encoded_rtd = (response[1] << 8) | response[2]
            if encoded_rtd & 0x01:
                fault_response = _transfer_exact(spi, [_FAULT_READ, 0x00], 2)
                self.last_fault_register = fault_response[1]
                self.last_faults = _decode_faults(fault_response[1])
                raise ValueError("MAX31865 reported a sensor fault")
            raw_rtd = encoded_rtd >> 1
            temperature_c = _temperature_from_raw(raw_rtd)
            if not self._minimum_temperature_c <= temperature_c <= self._maximum_temperature_c:
                raise ValueError("PT100 temperature outside application range")
            return temperature_c
        finally:
            if opened:
                try:
                    _write_config(spi, _CONFIG_3WIRE_50HZ)
                finally:
                    spi.close()


def _write_config(spi: SpiDevice, value: int) -> None:
    _transfer_exact(spi, [_CONFIG_WRITE, value], 2)


def _transfer_exact(spi: SpiDevice, payload: list[int], expected: int) -> list[int]:
    response = spi.transfer(payload)
    if len(response) != expected:
        raise ValueError("short SPI transfer")
    if any(not 0 <= value <= 0xFF for value in response):
        raise ValueError("SPI transfer returned a non-byte value")
    return response


def _decode_faults(register: int) -> tuple[str, ...]:
    return tuple(name for bit, name in _FAULT_FLAGS if register & bit)


def _temperature_from_raw(raw_rtd: int) -> float:
    if raw_rtd <= 0 or raw_rtd >= 0x7FFF:
        raise ValueError("impossible RTD ratio")
    resistance = raw_rtd * _REFERENCE_RESISTOR_OHM / 32768.0
    if resistance >= _PT100_R0_OHM:
        ratio = resistance / _PT100_R0_OHM
        discriminant = _CVD_A**2 - 4 * _CVD_B * (1 - ratio)
        if discriminant < 0:
            raise ArithmeticError("invalid Callendar-Van Dusen discriminant")
        temperature_c = (-_CVD_A + sqrt(discriminant)) / (2 * _CVD_B)
    else:
        temperature_c = _negative_temperature_from_resistance(resistance)
    if not isfinite(temperature_c):
        raise ArithmeticError("non-finite PT100 temperature")
    return temperature_c


def _negative_temperature_from_resistance(resistance: float) -> float:
    low = -200.0
    high = 0.0
    for _ in range(64):
        midpoint = (low + high) / 2
        candidate = _resistance_at_negative_temperature(midpoint)
        if candidate < resistance:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2


def _resistance_at_negative_temperature(temperature_c: float) -> float:
    return _PT100_R0_OHM * (
        1
        + _CVD_A * temperature_c
        + _CVD_B * temperature_c**2
        + _CVD_C * (temperature_c - 100) * temperature_c**3
    )
