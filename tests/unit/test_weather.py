from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Self
from urllib.parse import parse_qs, urlparse

import pytest

from freeze_protect.adapters.weather import OpenMeteoForecastClient
from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.models import SafetySettings

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def settings() -> SafetySettings:
    return SafetySettings(
        latitude=46.5547,
        longitude=15.6459,
        timezone="Europe/Ljubljana",
    )


def payload(days: int = 7) -> dict[str, object]:
    first = date(2026, 9, 11)
    return {
        "latitude": 46.5547,
        "longitude": 15.6459,
        "generationtime_ms": 0.1,
        "daily": {
            "time": [(first + timedelta(days=index)).isoformat() for index in range(days)],
            "temperature_2m_min": [6.0] * days,
        },
    }


def test_open_meteo_rejects_a_six_day_or_non_finite_payload() -> None:
    client = OpenMeteoForecastClient(lambda _request, _timeout: FakeResponse(payload(6)))

    with pytest.raises(AdapterError, match="exactly seven"):
        client.fetch(settings(), NOW)


def test_open_meteo_builds_configured_seven_day_query_and_parses_snapshot() -> None:
    requests: list[object] = []

    def urlopen(request: object, _timeout: float) -> FakeResponse:
        requests.append(request)
        return FakeResponse(payload())

    snapshot = OpenMeteoForecastClient(urlopen).fetch(settings(), NOW)

    query = parse_qs(urlparse(requests[0].full_url).query)  # type: ignore[attr-defined]
    assert query == {
        "latitude": ["46.5547"],
        "longitude": ["15.6459"],
        "daily": ["temperature_2m_min"],
        "forecast_days": ["7"],
        "timezone": ["Europe/Ljubljana"],
    }
    assert snapshot.daily_minima_c == (6.0,) * 7
    assert snapshot.fetched_at == NOW


def test_open_meteo_rejects_a_response_for_another_location() -> None:
    foreign = payload()
    foreign["latitude"] = 48.0

    with pytest.raises(AdapterError, match="location"):
        OpenMeteoForecastClient(
            lambda _request, _timeout: FakeResponse(foreign)
        ).fetch(settings(), NOW)
