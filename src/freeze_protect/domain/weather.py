"""Five-day weather contracts, independent of legacy seven-day forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEATHER_REFRESH_SECONDS = 900
WEATHER_FETCH_DEADLINE_SECONDS = 5
WEATHER_MAX_AGE_SECONDS = 1200
WEATHER_PROCESSING_BOUND_SECONDS = 30


def _number(value: object, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")


def _revision(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _timezone(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("timezone must be a valid IANA timezone")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("timezone must be a valid IANA timezone") from error


def _coordinates(latitude: float, longitude: float) -> None:
    _number(latitude, "latitude")
    _number(longitude, "longitude")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("coordinates are outside valid bounds")


@dataclass(frozen=True, slots=True)
class WeatherSettings:
    enabled: bool = False
    latitude: float | None = None
    longitude: float | None = None
    timezone: str = "Europe/Ljubljana"
    revision: int = 0

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be boolean")
        _revision(self.revision, "revision")
        _timezone(self.timezone)
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("coordinates must be configured together")
        if self.latitude is not None and self.longitude is not None:
            _coordinates(self.latitude, self.longitude)


@dataclass(frozen=True, slots=True)
class WeatherWindow:
    dates: tuple[date, ...]
    minima_c: tuple[float, ...]
    fetched_at: datetime
    requested_latitude: float
    requested_longitude: float
    timezone: str
    settings_revision: int
    generation: int

    def __post_init__(self) -> None:
        if type(self.dates) is not tuple or type(self.minima_c) is not tuple:
            raise ValueError("dates and minima must be immutable tuples")
        if len(self.dates) != 5 or len(self.minima_c) != 5:
            raise ValueError("weather requires exactly five dates and minima")
        if any(type(day) is not date for day in self.dates):
            raise ValueError("dates must be local calendar dates")
        if any(b != a + timedelta(days=1) for a, b in zip(self.dates, self.dates[1:])):
            raise ValueError("dates must be consecutive")
        for value in self.minima_c:
            _number(value, "minimum")
        if (
            not isinstance(self.fetched_at, datetime)
            or self.fetched_at.utcoffset() is None
        ):
            raise ValueError("fetched_at must be timezone aware")
        _coordinates(self.requested_latitude, self.requested_longitude)
        _timezone(self.timezone)
        _revision(self.settings_revision, "settings_revision")
        _revision(self.generation, "generation")


@dataclass(frozen=True, slots=True)
class WeatherObservation:
    window: WeatherWindow | None
    received_mono: float
    latest_attempt_ok: bool
    reason: str

    def __post_init__(self) -> None:
        _number(self.received_mono, "received_mono")
        if type(self.latest_attempt_ok) is not bool:
            raise ValueError("latest_attempt_ok must be boolean")
        if self.window is not None and not isinstance(self.window, WeatherWindow):
            raise ValueError("window must be a WeatherWindow")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be a string")


@dataclass(frozen=True, slots=True)
class WeatherEligibility:
    eligible: bool
    reason: str


@dataclass(frozen=True, slots=True)
class WeatherControlRecord:
    settings: WeatherSettings = WeatherSettings()
    user_off: bool = False
    fault_inhibited: bool = False
    active_marker: str | None = None
    control_revision: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.settings, WeatherSettings):
            raise TypeError("settings must be WeatherSettings")
        if type(self.user_off) is not bool or type(self.fault_inhibited) is not bool:
            raise ValueError("inhibitions must be boolean")
        if self.active_marker not in (None, "manual", "auto"):
            raise ValueError("invalid active marker")
        _revision(self.control_revision, "control_revision")


def evaluate_weather(
    settings: WeatherSettings,
    observation: WeatherObservation | None,
    now: datetime,
    now_mono: float,
) -> WeatherEligibility:
    """Validate process-local freshness; callers latch a failed time basis until refetch."""
    reason = _ineligible_reason(settings, observation, now, now_mono)
    return WeatherEligibility(reason is None, reason or "eligible")


def _ineligible_reason(
    settings: WeatherSettings,
    observation: WeatherObservation | None,
    now: datetime,
    now_mono: float,
) -> str | None:
    if not settings.enabled:
        return "disabled"
    if settings.latitude is None or settings.longitude is None:
        return "location_missing"
    if observation is None or observation.window is None:
        return "weather_missing"
    if not observation.latest_attempt_ok:
        return "latest_attempt_failed"
    window = observation.window
    if (
        window.settings_revision != settings.revision
        or window.timezone != settings.timezone
        or window.requested_latitude != settings.latitude
        or window.requested_longitude != settings.longitude
    ):
        return "settings_mismatch"
    if not isinstance(now, datetime) or now.utcoffset() is None:
        return "time_basis_invalid"
    if (
        isinstance(now_mono, bool)
        or not isinstance(now_mono, int | float)
        or not isfinite(now_mono)
    ):
        return "time_basis_invalid"
    age = now_mono - observation.received_mono
    wall_age = (now.astimezone(UTC) - window.fetched_at.astimezone(UTC)).total_seconds()
    if (
        age < 0
        or wall_age < 0
        or abs(wall_age - age) > WEATHER_PROCESSING_BOUND_SECONDS
    ):
        return "time_basis_invalid"
    if age >= WEATHER_MAX_AGE_SECONDS:
        return "weather_stale"
    today = now.astimezone(ZoneInfo(settings.timezone)).date()
    if window.dates != tuple(today + timedelta(days=i) for i in range(5)):
        return "coverage_invalid"
    if any(value < 5.0 for value in window.minima_c):
        return "cold_forecast"
    return None
