from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from math import isfinite
from typing import Protocol, Self, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen as stdlib_urlopen

from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.models import ForecastSnapshot, SafetySettings

_BASE_URL = "https://api.open-meteo.com/v1/forecast"


class _Response(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...

    def read(self) -> bytes: ...


UrlOpen = Callable[[Request, float], _Response]


def _urlopen(request: Request, timeout: float) -> _Response:
    return cast(_Response, stdlib_urlopen(request, timeout=timeout))


class OpenMeteoForecastClient:
    def __init__(self, request_opener: UrlOpen = _urlopen, timeout_s: float = 5.0) -> None:
        self._request_opener = request_opener
        self._timeout_s = timeout_s

    def fetch(self, settings: SafetySettings, now: datetime) -> ForecastSnapshot:
        if settings.latitude is None or settings.longitude is None:
            raise AdapterError("weather location is not configured")
        query = urlencode(
            {
                "latitude": settings.latitude,
                "longitude": settings.longitude,
                "daily": "temperature_2m_min",
                "forecast_days": 7,
                "timezone": settings.timezone,
            }
        )
        request = Request(
            f"{_BASE_URL}?{query}", headers={"Accept": "application/json"}
        )
        try:
            with self._request_opener(request, self._timeout_s) as response:
                decoded = json.loads(response.read().decode("utf-8"))
            return _parse_snapshot(decoded, settings, now)
        except (HTTPError, URLError, OSError) as error:
            raise AdapterError(f"Open-Meteo request failed: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise AdapterError(f"Open-Meteo response is invalid: {error}") from error


def _parse_snapshot(
    payload: object, settings: SafetySettings, now: datetime
) -> ForecastSnapshot:
    if not isinstance(payload, dict):
        raise TypeError("response must be an object")
    latitude = _finite_number(payload, "latitude")
    longitude = _finite_number(payload, "longitude")
    if settings.latitude is None or settings.longitude is None:
        raise ValueError("configured location is missing")
    if (
        abs(latitude - settings.latitude) > 0.01
        or abs(longitude - settings.longitude) > 0.01
    ):
        raise ValueError("response location does not match configuration")
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise TypeError("daily data is missing")
    return ForecastSnapshot(
        dates=_dates(daily.get("time")),
        daily_minima_c=_minima(daily.get("temperature_2m_min")),
        source_generated_at=None,
        fetched_at=now,
        latitude=latitude,
        longitude=longitude,
    )


def _dates(value: object) -> tuple[date, ...]:
    if not isinstance(value, list) or len(value) != 7:
        raise ValueError("forecast must contain exactly seven dates")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("forecast dates must be ISO date strings")
    return tuple(date.fromisoformat(item) for item in value)


def _minima(value: object) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != 7:
        raise ValueError("forecast must contain exactly seven minima")
    minima = tuple(_finite_value(item) for item in value)
    return minima


def _finite_number(payload: dict[object, object], key: str) -> float:
    return _finite_value(payload.get(key))


def _finite_value(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("forecast values must be numeric")
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError("forecast values must be finite")
    return numeric
