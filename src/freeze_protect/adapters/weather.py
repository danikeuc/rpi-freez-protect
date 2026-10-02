from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from math import isfinite
from typing import Protocol, Self, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.request import urlopen as stdlib_urlopen
from zoneinfo import ZoneInfo

from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.models import ForecastSnapshot, SafetySettings
from freeze_protect.domain.weather import WeatherSettings, WeatherWindow

_BASE_URL = "https://api.open-meteo.com/v1/forecast"


class _Response(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...

    def read(self, size: int = -1) -> bytes: ...

    def geturl(self) -> str: ...

    @property
    def status(self) -> int: ...


UrlOpen = Callable[[Request, float], _Response]


def _urlopen(request: Request, timeout: float) -> _Response:
    return cast(_Response, stdlib_urlopen(request, timeout=timeout))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        raise AdapterError("Open-Meteo redirect rejected")


def _window_urlopen(request: Request, timeout: float) -> _Response:
    # Standard HTTPSHandler uses certificate and hostname verification.
    return cast(_Response, build_opener(_NoRedirect()).open(request, timeout=timeout))


class OpenMeteoForecastClient:
    def __init__(
        self, request_opener: UrlOpen = _urlopen, timeout_s: float = 5.0
    ) -> None:
        self._request_opener = request_opener
        self._window_opener = (
            _window_urlopen if request_opener is _urlopen else request_opener
        )
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
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as error:
            raise AdapterError(f"Open-Meteo response is invalid: {error}") from error

    def fetch_window(
        self, settings: WeatherSettings, now: datetime, generation: int
    ) -> WeatherWindow:
        if settings.latitude is None or settings.longitude is None:
            raise AdapterError("weather location is not configured")
        query = urlencode(
            {
                "latitude": settings.latitude,
                "longitude": settings.longitude,
                "daily": "temperature_2m_min",
                "forecast_days": 5,
                "temperature_unit": "celsius",
                "timezone": settings.timezone,
            }
        )
        request = Request(
            f"{_BASE_URL}?{query}", headers={"Accept": "application/json"}
        )
        try:
            with self._window_opener(request, min(self._timeout_s, 5.0)) as response:
                if response.geturl() != request.full_url or response.status != 200:
                    raise AdapterError("Open-Meteo redirect or status rejected")
                body = response.read(65537)
                if len(body) > 65536:
                    raise ValueError("response too large")
                decoded = json.loads(
                    body.decode("utf-8"), object_pairs_hook=_unique_fields
                )
            return _parse_window(decoded, settings, now, generation)
        except (HTTPError, URLError, OSError) as error:
            raise AdapterError("Open-Meteo request failed") from error
        except (
            UnicodeDecodeError,
            ValueError,
            TypeError,
            RecursionError,
            OverflowError,
        ) as error:
            raise AdapterError("Open-Meteo response is invalid") from error


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response field")
        result[key] = value
    return result


def _parse_window(
    payload: object, settings: WeatherSettings, now: datetime, generation: int
) -> WeatherWindow:
    if not isinstance(payload, dict):
        raise TypeError("response must be an object")
    latitude = _finite_number(payload, "latitude")
    longitude = _finite_number(payload, "longitude")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("invalid grid coordinates")
    if payload.get("timezone") != settings.timezone:
        raise ValueError("timezone mismatch")
    units = payload.get("daily_units")
    if (
        not isinstance(units, dict)
        or units.get("temperature_2m_min") != "°C"
        or units.get("time") != "iso8601"
    ):
        raise ValueError("invalid daily units")
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise TypeError("daily data is missing")
    times, minima = daily.get("time"), daily.get("temperature_2m_min")
    if (
        not isinstance(times, list)
        or len(times) != 5
        or not all(isinstance(day, str) for day in times)
    ):
        raise ValueError("expected five ISO dates")
    if not isinstance(minima, list) or len(minima) != 5:
        raise ValueError("expected five minima")
    dates = tuple(date.fromisoformat(day) for day in times)
    today = now.astimezone(ZoneInfo(settings.timezone)).date()
    if dates != tuple(today + timedelta(days=i) for i in range(5)):
        raise ValueError("local date coverage mismatch")
    if settings.latitude is None or settings.longitude is None:
        raise ValueError("location missing")
    return WeatherWindow(
        dates,
        tuple(_finite_value(value) for value in minima),
        now,
        settings.latitude,
        settings.longitude,
        settings.timezone,
        settings.revision,
        generation,
    )


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
