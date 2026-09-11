from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite


class ControllerState(str, Enum):
    STARTING = "STARTING"
    MONITORING = "MONITORING"
    PROTECTING = "PROTECTING"
    RELEASE_PENDING = "RELEASE_PENDING"
    MANUAL_LOCK = "MANUAL_LOCK"
    FAULT = "FAULT"


class RelayCommand(str, Enum):
    OPEN = "OPEN"
    CLOSE_OR_PROTECT = "CLOSE_OR_PROTECT"
    STOP = "STOP"


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


@dataclass(frozen=True, slots=True)
class ForecastSnapshot:
    daily_minima_c: tuple[float, ...]
    fetched_at: datetime

    def __post_init__(self) -> None:
        if any(not isfinite(value) for value in self.daily_minima_c):
            raise ValueError("daily_minima_c must contain finite values")

    def has_minima_above(self, threshold_c: float, days: int) -> bool:
        if days <= 0:
            raise ValueError("days must be positive")
        if not isfinite(threshold_c):
            raise ValueError("threshold_c must be finite")
        if len(self.daily_minima_c) < days:
            return False
        return all(value > threshold_c for value in self.daily_minima_c[:days])


@dataclass(frozen=True, slots=True)
class SafetySettings:
    protection_threshold_c: float = 1.0
    release_threshold_c: float = 5.0
    release_days: int = 7
    sensor_stale_after_s: int = 900
    minimum_protection_dwell_s: int = 300
    settings_version: int = 1

    def __post_init__(self) -> None:
        if not isfinite(self.protection_threshold_c):
            raise ValueError("protection_threshold_c must be finite")
        if not isfinite(self.release_threshold_c):
            raise ValueError("release_threshold_c must be finite")
        if self.release_threshold_c <= self.protection_threshold_c:
            raise ValueError(
                "release_threshold_c must exceed protection_threshold_c"
            )
        if self.release_days <= 0:
            raise ValueError("release_days must be positive")
        if self.sensor_stale_after_s <= 0:
            raise ValueError("sensor_stale_after_s must be positive")
        if self.minimum_protection_dwell_s <= 0:
            raise ValueError("minimum_protection_dwell_s must be positive")
        if self.settings_version <= 0:
            raise ValueError("settings_version must be positive")


@dataclass(frozen=True, slots=True)
class Decision:
    state: ControllerState
    command: RelayCommand
    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("reason must not be empty")


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
