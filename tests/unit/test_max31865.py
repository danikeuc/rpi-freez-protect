from __future__ import annotations

from datetime import UTC, datetime
from math import isclose
from types import SimpleNamespace

import pytest

import freeze_protect.adapters.max31865 as max31865_module
from freeze_protect.adapters.max31865 import LinuxSpiDevice, Max31865TemperatureSource
from freeze_protect.domain.models import SensorHealth

NOW = datetime(2026, 9, 21, 20, tzinfo=UTC)


def encoded_rtd_for_temperature(temperature_c: float) -> int:
    r0 = 100.0
    a = 3.9083e-3
    b = -5.775e-7
    c = -4.183e-12
    if temperature_c >= 0:
        resistance = r0 * (1 + a * temperature_c + b * temperature_c**2)
    else:
        resistance = r0 * (
            1
            + a * temperature_c
            + b * temperature_c**2
            + c * (temperature_c - 100) * temperature_c**3
        )
    raw = round(resistance / 430.0 * 32768)
    return raw << 1


class FakeSpiDevice:
    def __init__(
        self,
        *,
        encoded_rtd: int,
        fault_register: int = 0,
        short_rtd_read: bool = False,
        fail_rtd_read: bool = False,
    ) -> None:
        self.encoded_rtd = encoded_rtd
        self.fault_register = fault_register
        self.short_rtd_read = short_rtd_read
        self.fail_rtd_read = fail_rtd_read
        self.operations: list[tuple[str, object]] = []

    def open(self) -> None:
        self.operations.append(("open", None))

    def transfer(self, payload: list[int]) -> list[int]:
        self.operations.append(("transfer", tuple(payload)))
        if payload == [0x01, 0x00, 0x00]:
            if self.fail_rtd_read:
                self.fail_rtd_read = False
                raise OSError("SPI transfer failed")
            if self.short_rtd_read:
                return [0x00]
            return [
                0x00,
                (self.encoded_rtd >> 8) & 0xFF,
                self.encoded_rtd & 0xFF,
            ]
        if payload == [0x07, 0x00]:
            return [0x00, self.fault_register]
        return [0x00] * len(payload)

    def close(self) -> None:
        self.operations.append(("close", None))


def source_for(
    spi: FakeSpiDevice, sleeps: list[float] | None = None
) -> Max31865TemperatureSource:
    sleep_calls = sleeps if sleeps is not None else []
    return Max31865TemperatureSource(
        spi_factory=lambda: spi,
        clock=lambda: NOW,
        sleeper=sleep_calls.append,
    )


def test_one_shot_sequence_returns_a_positive_temperature_and_disables_bias() -> None:
    spi = FakeSpiDevice(encoded_rtd=encoded_rtd_for_temperature(25.0))
    sleeps: list[float] = []

    reading = source_for(spi, sleeps).read()

    assert reading.health is SensorHealth.HEALTHY
    assert reading.value_c is not None
    assert isclose(reading.value_c, 25.0, abs_tol=0.03)
    assert reading.observed_at == NOW
    assert sleeps == [0.010, 0.066]
    assert spi.operations == [
        ("open", None),
        ("transfer", (0x80, 0x13)),
        ("transfer", (0x80, 0x91)),
        ("transfer", (0x80, 0xB1)),
        ("transfer", (0x01, 0x00, 0x00)),
        ("transfer", (0x80, 0x11)),
        ("close", None),
    ]


def test_negative_temperature_uses_the_full_callendar_van_dusen_branch() -> None:
    spi = FakeSpiDevice(encoded_rtd=encoded_rtd_for_temperature(-20.0))

    reading = source_for(spi).read()

    assert reading.health is SensorHealth.HEALTHY
    assert reading.value_c is not None
    assert isclose(reading.value_c, -20.0, abs_tol=0.03)


def test_fault_bit_returns_invalid_and_decodes_the_fault_register() -> None:
    encoded = encoded_rtd_for_temperature(5.0) | 0x01
    spi = FakeSpiDevice(encoded_rtd=encoded, fault_register=0x44)
    source = source_for(spi)

    reading = source.read()

    assert reading.value_c is None
    assert reading.health is SensorHealth.INVALID
    assert source.last_fault_register == 0x44
    assert source.last_faults == ("RTD_LOW_THRESHOLD", "OVER_UNDERVOLTAGE")
    assert ("transfer", (0x07, 0x00)) in spi.operations
    assert spi.operations[-2:] == [
        ("transfer", (0x80, 0x11)),
        ("close", None),
    ]


@pytest.mark.parametrize("raw", [0, 0x7FFF])
def test_impossible_rtd_ratio_is_invalid(raw: int) -> None:
    spi = FakeSpiDevice(encoded_rtd=raw << 1)

    reading = source_for(spi).read()

    assert reading.value_c is None
    assert reading.health is SensorHealth.INVALID


def test_short_transfer_is_invalid_and_still_disables_bias() -> None:
    spi = FakeSpiDevice(
        encoded_rtd=encoded_rtd_for_temperature(5.0), short_rtd_read=True
    )

    reading = source_for(spi).read()

    assert reading.value_c is None
    assert reading.health is SensorHealth.INVALID
    assert spi.operations[-2:] == [
        ("transfer", (0x80, 0x11)),
        ("close", None),
    ]


def test_spi_error_is_stale_never_reuses_a_previous_healthy_value() -> None:
    spi = FakeSpiDevice(encoded_rtd=encoded_rtd_for_temperature(5.0))
    source = source_for(spi)
    assert source.read().health is SensorHealth.HEALTHY
    spi.fail_rtd_read = True

    failed = source.read()

    assert failed.value_c is None
    assert failed.health is SensorHealth.STALE
    assert spi.operations[-2:] == [
        ("transfer", (0x80, 0x11)),
        ("close", None),
    ]


@pytest.mark.parametrize("temperature_c", [-51.0, 121.0])
def test_application_range_rejects_implausible_pipe_temperature(
    temperature_c: float,
) -> None:
    spi = FakeSpiDevice(encoded_rtd=encoded_rtd_for_temperature(temperature_c))

    reading = source_for(spi).read()

    assert reading.value_c is None
    assert reading.health is SensorHealth.INVALID


def test_linux_spi_closes_device_when_configuration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ConfigurationFailingDevice:
        def __init__(self) -> None:
            self.closed = False
            self.max_speed_hz = 0
            self.bits_per_word = 0

        def open_path(self, _path: str) -> None:
            pass

        @property
        def mode(self) -> int:
            return 0

        @mode.setter
        def mode(self, _value: int) -> None:
            raise OSError("mode rejected")

        def close(self) -> None:
            self.closed = True

    raw_device = ConfigurationFailingDevice()
    monkeypatch.setattr(
        max31865_module,
        "import_module",
        lambda _name: SimpleNamespace(SpiDev=lambda: raw_device),
    )

    with pytest.raises(OSError, match="mode rejected"):
        LinuxSpiDevice().open()

    assert raw_device.closed is True


def test_linux_spi_uses_the_exact_production_bus_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ConfiguredDevice:
        def __init__(self) -> None:
            self.path = ""
            self.max_speed_hz = 0
            self.mode = 0
            self.bits_per_word = 0
            self.closed = False

        def open_path(self, path: str) -> None:
            self.path = path

        def xfer2(self, payload: list[int]) -> list[int]:
            return payload

        def close(self) -> None:
            self.closed = True

    raw_device = ConfiguredDevice()
    monkeypatch.setattr(
        max31865_module,
        "import_module",
        lambda _name: SimpleNamespace(SpiDev=lambda: raw_device),
    )
    spi = LinuxSpiDevice()

    spi.open()
    response = spi.transfer([0x01, 0x00, 0x00])
    spi.close()

    assert raw_device.path == "/dev/spidev0.0"
    assert raw_device.max_speed_hz == 500_000
    assert raw_device.mode == 1
    assert raw_device.bits_per_word == 8
    assert response == [0x01, 0x00, 0x00]
    assert raw_device.closed is True
