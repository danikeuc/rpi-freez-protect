from datetime import UTC, datetime, timedelta
from pathlib import Path

from freeze_protect.adapters.ds18b20 import Ds18b20TemperatureSource
from freeze_protect.domain.models import SafetySettings, SensorHealth

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


def test_ds18b20_reads_crc_valid_millidegree_value(tmp_path: Path) -> None:
    device = tmp_path / "28-00000abc" / "w1_slave"
    device.parent.mkdir()
    device.write_text("9e 01 4b 46 7f ff 02 10 83 : crc=83 YES\n9e 01 4b 46 7f ff 02 10 83 t=25375\n")

    reading = Ds18b20TemperatureSource(
        devices_path=tmp_path,
        settings_provider=lambda: SafetySettings(sensor_device_id="28-00000abc"),
        clock=lambda: NOW,
    ).read()

    assert reading.value_c == 25.375
    assert reading.health is SensorHealth.HEALTHY


def test_ds18b20_returns_stale_when_the_kernel_file_is_old(tmp_path: Path) -> None:
    device = tmp_path / "28-00000abc" / "w1_slave"
    device.parent.mkdir()
    device.write_text("aa : crc=aa YES\naa t=6000\n")
    stale_at = (NOW - timedelta(seconds=121)).timestamp()
    device.touch()
    device.chmod(0o600)
    import os

    os.utime(device, (stale_at, stale_at))

    reading = Ds18b20TemperatureSource(
        devices_path=tmp_path,
        settings_provider=lambda: SafetySettings(sensor_device_id="28-00000abc"),
        clock=lambda: NOW,
    ).read()

    assert reading.value_c is None
    assert reading.health is SensorHealth.STALE


def test_ds18b20_returns_calibration_required_before_commissioning(tmp_path: Path) -> None:
    reading = Ds18b20TemperatureSource(
        devices_path=tmp_path,
        settings_provider=SafetySettings,
        clock=lambda: NOW,
    ).read()

    assert reading.value_c is None
    assert reading.health is SensorHealth.CALIBRATION_REQUIRED
