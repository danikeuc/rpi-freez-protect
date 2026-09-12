from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from freeze_protect.domain.models import SafetySettings, SensorHealth, TemperatureReading

_TEMPERATURE_PATTERN = re.compile(r"(?:^|\s)t=(-?\d+)(?:\s|$)")


class Ds18b20TemperatureSource:
    def __init__(
        self,
        *,
        devices_path: Path = Path("/sys/bus/w1/devices"),
        settings_provider: Callable[[], SafetySettings],
        clock: Callable[[], datetime],
    ) -> None:
        self._devices_path = devices_path
        self._settings_provider = settings_provider
        self._clock = clock

    def read(self) -> TemperatureReading:
        settings = self._settings_provider()
        now = self._clock()
        if settings.sensor_device_id is None:
            return TemperatureReading(None, now, SensorHealth.CALIBRATION_REQUIRED)
        device = self._devices_path / settings.sensor_device_id / "w1_slave"
        try:
            observed_at = datetime.fromtimestamp(device.stat().st_mtime, UTC)
            if (now - observed_at).total_seconds() > settings.sensor_stale_after_s:
                return TemperatureReading(None, observed_at, SensorHealth.STALE)
            lines = device.read_text(encoding="ascii").splitlines()
        except OSError:
            return TemperatureReading(None, now, SensorHealth.STALE)
        if len(lines) < 2 or not lines[0].rstrip().endswith("YES"):
            return TemperatureReading(None, observed_at, SensorHealth.INVALID)
        match = _TEMPERATURE_PATTERN.search(lines[1])
        if match is None:
            return TemperatureReading(None, observed_at, SensorHealth.INVALID)
        return TemperatureReading(
            value_c=int(match.group(1)) / 1000,
            observed_at=observed_at,
            health=SensorHealth.HEALTHY,
        )
