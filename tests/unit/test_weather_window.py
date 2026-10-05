from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Self
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from freeze_protect.adapters.weather import OpenMeteoForecastClient
from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.weather import (
    WeatherObservation,
    WeatherSettings,
    evaluate_weather,
)

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
SETTINGS = WeatherSettings(True, 46.5, 15.5)


def payload() -> dict:
    return {
        "latitude": 46.6,
        "longitude": 15.6,
        "timezone": "Europe/Ljubljana",
        "daily_units": {"time": "iso8601", "temperature_2m_min": "°C"},
        "daily": {
            "time": [f"2026-10-0{i}" for i in range(3, 8)],
            "temperature_2m_min": [5.0] * 5,
        },
    }


class Response:
    def __init__(
        self, body: bytes, url: str = "https://api.open-meteo.com/v1/forecast"
    ):
        self.body = body
        self.url = url
        if url == "https://api.open-meteo.com/v1/forecast":
            self.url += "?" + urlencode(
                {
                    "latitude": 46.5,
                    "longitude": 15.5,
                    "daily": "temperature_2m_min,weather_code",
                    "forecast_days": 5,
                    "temperature_unit": "celsius",
                    "timezone": "Europe/Ljubljana",
                }
            )
        self.closed = False
        self.read_sizes: list[int] = []
        self.status = 200

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self.body[:size] if size >= 0 else self.body

    def geturl(self) -> str:
        return self.url


def test_query_grid_coordinate_and_bounded_read() -> None:
    response = Response(json.dumps(payload()).encode())
    requests = []

    def opener(request, timeout):
        requests.append(request)
        assert timeout <= 5
        response.url = request.full_url
        return response

    window = OpenMeteoForecastClient(opener).fetch_window(SETTINGS, NOW, 3)
    assert urlsplit(requests[0].full_url).scheme == "https"
    assert parse_qs(urlsplit(requests[0].full_url).query) == {
        "latitude": ["46.5"],
        "longitude": ["15.5"],
        "timezone": ["Europe/Ljubljana"],
        "daily": ["temperature_2m_min,weather_code"],
        "forecast_days": ["5"],
        "temperature_unit": ["celsius"],
    }
    assert window.requested_latitude == 46.5
    assert window.requested_longitude == 15.5
    assert window.generation == 3
    assert window.minima_c == (5.0,) * 5
    assert response.read_sizes == [65537]
    assert response.closed


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", 91),
        ("longitude", -181),
        ("latitude", True),
        ("latitude", float("inf")),
        ("latitude", 10**400),
        ("timezone", "UTC"),
        ("timezone", None),
        ("daily_units", {}),
        ("daily_units", {"temperature_2m_min": "°F"}),
        ("daily", []),
    ],
)
def test_invalid_metadata(field, value) -> None:
    data = payload()
    data[field] = value
    response = Response(json.dumps(data).encode())
    with pytest.raises(AdapterError):
        OpenMeteoForecastClient(lambda *_: response).fetch_window(SETTINGS, NOW, 0)
    assert response.closed


@pytest.mark.parametrize(
    "value", [True, None, "5", float("nan"), float("inf"), 10**400]
)
def test_bad_minimum(value) -> None:
    data = payload()
    data["daily"]["temperature_2m_min"][0] = value
    with pytest.raises(AdapterError):
        OpenMeteoForecastClient(
            lambda *_: Response(json.dumps(data).encode())
        ).fetch_window(SETTINGS, NOW, 0)


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"\xff",
        b" " * 65537,
        b"[" * 2000 + b"]" * 2000,
        b'{"latitude":1,"latitude":2}',
        b"null",
    ],
    ids=["json", "utf8", "size", "deep", "duplicate", "null"],
)
def test_bad_bodies_are_sanitized(body) -> None:
    response = Response(body)
    with pytest.raises(AdapterError) as caught:
        OpenMeteoForecastClient(lambda *_: response).fetch_window(SETTINGS, NOW, 0)
    assert str(caught.value) == "Open-Meteo response is invalid"
    assert response.closed


@pytest.mark.parametrize(
    "url,status",
    [
        ("http://api.open-meteo.com/v1/forecast", 200),
        ("https://other.example/", 200),
        ("https://api.open-meteo.com/v1/forecast", 302),
    ],
)
def test_redirect_and_insecure_response_rejected(url, status) -> None:
    response = Response(json.dumps(payload()).encode(), url)
    response.url = url
    response.status = status
    with pytest.raises(AdapterError):
        OpenMeteoForecastClient(lambda *_: response).fetch_window(SETTINGS, NOW, 0)


@pytest.mark.parametrize(
    "times,minima",
    [
        (["2026-10-03"] * 5, [6.0] * 5),
        ([f"2026-10-0{i}" for i in range(4, 9)], [6.0] * 5),
        ([f"2026-10-0{i}" for i in range(3, 7)], [6.0] * 5),
        ([f"2026-10-0{i}" for i in range(3, 8)], [6.0] * 4),
        ([f"2026-10-0{i}" for i in range(3, 8)], [6.0] * 6),
        ([123] * 5, [6.0] * 5),
    ],
)
def test_invalid_daily_coverage(times, minima) -> None:
    data = payload()
    data["daily"] = {"time": times, "temperature_2m_min": minima}
    with pytest.raises(AdapterError, match="response is invalid"):
        OpenMeteoForecastClient(
            lambda *_: Response(json.dumps(data).encode())
        ).fetch_window(SETTINGS, NOW, 0)


def test_exact_body_limit_accepted() -> None:
    body = json.dumps(payload()).encode()
    response = Response(body + b" " * (65536 - len(body)))
    assert (
        OpenMeteoForecastClient(lambda *_: response)
        .fetch_window(SETTINGS, NOW, 0)
        .minima_c
        == (5.0,) * 5
    )


def test_default_transport_redirect_handler_rejects_before_following() -> None:
    from urllib.request import Request

    from freeze_protect.adapters.weather import _NoRedirect

    with pytest.raises(AdapterError, match="redirect rejected"):
        _NoRedirect().redirect_request(
            Request("https://api.open-meteo.com/v1/forecast"),
            None,
            302,
            "Found",
            {},
            "https://api.open-meteo.com/new",
        )


def test_network_error_is_sanitized() -> None:
    from urllib.error import URLError

    def opener(*_):
        raise URLError("provider-body-or-secret")

    with pytest.raises(AdapterError, match="^Open-Meteo request failed$"):
        OpenMeteoForecastClient(opener).fetch_window(SETTINGS, NOW, 0)


@pytest.mark.parametrize(
    "codes,expected",
    [
        ([0, 3, 61, 71, 97], (0, 3, 61, 71, 97)),
        (None, ()),
        ([], ()),
        ([0] * 4, ()),
        ([0] * 6, ()),
        ([0, 1, 2, 3, None], ()),
        ([False] * 5, ()),
        ([0.0] * 5, ()),
        (["0"] * 5, ()),
        ([4] * 5, ()),
        ([100] * 5, ()),
        ([float("nan")] * 5, ()),
        ([{}] * 5, ()),
        ({"0": 0}, ()),
    ],
)
@pytest.mark.parametrize("minimum", [4.9, 5.0])
def test_optional_codes_never_change_temperature_eligibility(codes, expected, minimum):
    data = payload()
    data["daily_units"]["weather_code"] = "wmo code"
    data["daily"]["weather_code"] = codes
    data["daily"]["temperature_2m_min"] = [minimum] * 5
    window = OpenMeteoForecastClient(
        lambda *_: Response(json.dumps(data).encode())
    ).fetch_window(SETTINGS, NOW, 0)
    assert window.weather_codes == expected
    decision = evaluate_weather(
        SETTINGS, WeatherObservation(window, 100.0, True, "success"), NOW, 100.0
    )
    assert decision.eligible is (minimum >= 5.0)
    assert decision.reason == ("eligible" if minimum >= 5.0 else "cold_forecast")


@pytest.mark.parametrize("units", [None, "", "unknown", 1])
def test_optional_code_units_do_not_invalidate_temperature_window(units):
    data = payload()
    data["daily"]["weather_code"] = [0] * 5
    data["daily_units"]["weather_code"] = units
    window = OpenMeteoForecastClient(
        lambda *_: Response(json.dumps(data).encode())
    ).fetch_window(SETTINGS, NOW, 0)
    assert window.weather_codes == ()
    assert window.minima_c == (5.0,) * 5


def test_legacy_provider_response_without_codes_remains_eligible():
    window = OpenMeteoForecastClient(
        lambda *_: Response(json.dumps(payload()).encode())
    ).fetch_window(SETTINGS, NOW, 0)
    assert window.weather_codes == ()
    assert evaluate_weather(
        SETTINGS, WeatherObservation(window, 100.0, True, "success"), NOW, 100.0
    ).eligible
