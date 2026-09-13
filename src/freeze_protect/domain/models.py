from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from math import isfinite
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ControllerState(str, Enum):
    STARTING = "STARTING"
    FROST_PROTECTION = "FROST_PROTECTION"
    NORMAL = "NORMAL"
    TIMED_SHOWER = "TIMED_SHOWER"
    FAULT = "FAULT"


class ActuatorCommand(str, Enum):
    DRAIN = "DRAIN"
    SUPPLY = "SUPPLY"


class SensorHealth(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    INVALID = "INVALID"
    CALIBRATION_REQUIRED = "CALIBRATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class TemperatureReading:
    value_c: float | None
    observed_at: datetime
    health: SensorHealth

    def __post_init__(self) -> None:
        if self.health is SensorHealth.HEALTHY and self.value_c is None:
            raise ValueError("healthy readings require value_c")
        if self.value_c is not None and not isfinite(self.value_c):
            raise ValueError("value_c must be finite")
        _require_aware(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class ForecastSnapshot:
    dates: tuple[date, ...]
    daily_minima_c: tuple[float, ...]
    source_generated_at: datetime | None
    fetched_at: datetime
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if len(self.dates) != 7 or len(self.daily_minima_c) != 7:
            raise ValueError("forecast must contain exactly seven daily values")
        if any(not isfinite(value) for value in self.daily_minima_c):
            raise ValueError("daily_minima_c must contain finite values")
        if any(
            later != earlier.fromordinal(earlier.toordinal() + 1)
            for earlier, later in zip(self.dates, self.dates[1:])
        ):
            raise ValueError("forecast dates must be consecutive")
        if not isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("forecast latitude must be within -90..90")
        if not isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("forecast longitude must be within -180..180")
        _require_aware(self.fetched_at, "fetched_at")
        if self.source_generated_at is not None:
            _require_aware(self.source_generated_at, "source_generated_at")

    def is_eligible(self, settings: SafetySettings, now: datetime) -> bool:
        if not self.is_fresh(now, settings.forecast_stale_after_s):
            return False
        if settings.latitude is None or settings.longitude is None:
            return False
        if (
            abs(self.latitude - settings.latitude) > 0.01
            or abs(self.longitude - settings.longitude) > 0.01
        ):
            return False
        current_local_date = now.astimezone(ZoneInfo(settings.timezone)).date()
        return (
            self.dates[0] == current_local_date
            and len(self.daily_minima_c) == settings.forecast_days
            and all(value > settings.forecast_threshold_c for value in self.daily_minima_c)
        )

    def is_fresh(self, now: datetime, stale_after_s: int) -> bool:
        _require_aware(now, "now")
        return 0 <= (now - self.fetched_at).total_seconds() <= stale_after_s


@dataclass(frozen=True, slots=True)
class SafetySettings:
    protection_threshold_c: float = 5.0
    release_threshold_c: float = 7.0
    forecast_threshold_c: float = 5.0
    forecast_days: int = 7
    sensor_stale_after_s: int = 120
    forecast_stale_after_s: int = 21_600
    timed_shower_default_s: int = 600
    timed_shower_max_s: int = 1_800
    latitude: float | None = None
    longitude: float | None = None
    timezone: str = "Europe/Ljubljana"
    sensor_device_id: str | None = None
    sensor_commissioned: bool = False
    settings_version: int = 1

    def __post_init__(self) -> None:
        for name, value in (
            ("protection_threshold_c", self.protection_threshold_c),
            ("release_threshold_c", self.release_threshold_c),
            ("forecast_threshold_c", self.forecast_threshold_c),
        ):
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.release_threshold_c <= self.protection_threshold_c:
            raise ValueError("release_threshold_c must exceed protection_threshold_c")
        if self.forecast_days != 7:
            raise ValueError("forecast_days must equal seven")
        for name, value in (
            ("sensor_stale_after_s", self.sensor_stale_after_s),
            ("forecast_stale_after_s", self.forecast_stale_after_s),
            ("timed_shower_default_s", self.timed_shower_default_s),
            ("timed_shower_max_s", self.timed_shower_max_s),
            ("settings_version", self.settings_version),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.timed_shower_default_s > self.timed_shower_max_s:
            raise ValueError("timed_shower_default_s must not exceed maximum")
        if self.timed_shower_max_s > 1_800:
            raise ValueError("timed_shower_max_s must not exceed 1800")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be configured together")
        if self.latitude is not None and (
            not isfinite(self.latitude) or not -90 <= self.latitude <= 90
        ):
            raise ValueError("latitude must be within -90..90")
        if self.longitude is not None and (
            not isfinite(self.longitude) or not -180 <= self.longitude <= 180
        ):
            raise ValueError("longitude must be within -180..180")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        if self.sensor_device_id is not None and not self.sensor_device_id.startswith("28-"):
            raise ValueError("sensor_device_id must start with 28-")


@dataclass(frozen=True, slots=True)
class Decision:
    state: ControllerState
    command: ActuatorCommand
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("reason must not be empty")


@dataclass(frozen=True, slots=True)
class ActuatorReceipt:
    command: ActuatorCommand
    request_id: str
    gpio_26: int
    gpio_20: int
    flow_revision: str

    def __post_init__(self) -> None:
        if not self.request_id or not self.flow_revision:
            raise ValueError("request_id and flow_revision must not be empty")
        expected_level = 0 if self.command is ActuatorCommand.SUPPLY else 1
        if (self.gpio_26, self.gpio_20) != (expected_level, expected_level):
            raise ValueError("receipt must confirm the paired GPIO levels")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    id: str
    occurred_at: datetime
    event_type: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.event_type:
            raise ValueError("event_type must not be empty")
        _require_aware(self.occurred_at, "occurred_at")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
