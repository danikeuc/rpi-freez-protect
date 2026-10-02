from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from freeze_protect.domain.weather import (
    WeatherObservation,
    WeatherSettings,
    WeatherWindow,
    evaluate_weather,
)

NOW = datetime(2026, 10, 3, 12, tzinfo=ZoneInfo("Europe/Ljubljana"))
SETTINGS = WeatherSettings(True, 46.0, 14.0, "Europe/Ljubljana", 0)


def window(**changes):
    values = {
        "dates": tuple(NOW.date() + timedelta(days=i) for i in range(5)),
        "minima_c": (5.0, 5.1, 5.0, 5.1, 5.0),
        "fetched_at": NOW,
        "requested_latitude": 46.0,
        "requested_longitude": 14.0,
        "timezone": "Europe/Ljubljana",
        "settings_revision": 0,
        "generation": 1,
    }
    values.update(changes)
    return WeatherWindow(**values)


def eligible(snapshot=None, *, settings=SETTINGS, now=NOW, mono=100.0, ok=True):
    return evaluate_weather(
        settings, WeatherObservation(snapshot or window(), 100.0, ok, "test"), now, mono
    ).eligible


def test_threshold_inclusive():
    assert eligible()
    assert not eligible(window(minima_c=(5.0, 5.1, 4.9, 5.0, 5.0)))


@pytest.mark.parametrize(
    "minima",
    [
        (5.0,) * 4,
        (5.0,) * 6,
        (True,) * 5,
        (None,) * 5,
        (float("nan"),) * 5,
        (float("inf"),) * 5,
    ],
)
def test_invalid_values(minima):
    with pytest.raises(ValueError):
        window(minima_c=minima)


@pytest.mark.parametrize(
    "offsets", [(0, 1, 2, 3), (0, 1, 2, 3, 4, 5), (0, 1, 1, 3, 4), (0, 1, 2, 3, 5)]
)
def test_invalid_dates(offsets):
    with pytest.raises(ValueError):
        window(dates=tuple(NOW.date() + timedelta(days=i) for i in offsets))


def test_provenance_disabled_failed_attempt_and_missing():
    assert not eligible(settings=replace(SETTINGS, enabled=False))
    assert not eligible(ok=False)
    assert not eligible(window(timezone="UTC"))
    assert not eligible(window(settings_revision=1))
    assert not eligible(window(requested_latitude=45.0))
    assert not evaluate_weather(SETTINGS, None, NOW, 100.0).eligible


@pytest.mark.parametrize("age,result", [(1199, True), (1200, False), (-1, False)])
def test_monotonic_freshness(age, result):
    assert eligible(now=NOW + timedelta(seconds=age), mono=100.0 + age) is result


def test_clock_discrepancy():
    assert not eligible(now=NOW - timedelta(seconds=1), mono=101.0)
    assert not eligible(now=NOW + timedelta(seconds=131), mono=200.0)
    assert eligible(now=NOW + timedelta(seconds=130), mono=200.0)


def test_midnight_and_dst_coverage():
    late = NOW.replace(hour=23, minute=59)
    w = window(fetched_at=late)
    assert not eligible(w, now=late + timedelta(minutes=2), mono=220.0)
    before = datetime(2026, 10, 25, 2, 59, tzinfo=ZoneInfo("Europe/Ljubljana"), fold=0)
    after = datetime(2026, 10, 25, 2, 1, tzinfo=ZoneInfo("Europe/Ljubljana"), fold=1)
    dst_window = window(
        fetched_at=before,
        dates=tuple(before.date() + timedelta(days=i) for i in range(5)),
    )
    assert eligible(dst_window, now=after, mono=220.0)
    assert not eligible(dst_window, now=after, mono=101.0)
    assert after.astimezone(UTC) > before.astimezone(UTC)


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": 1},
        {"latitude": True},
        {"revision": True},
        {"timezone": "invalid"},
        {"longitude": None},
    ],
)
def test_settings_validation(changes):
    with pytest.raises(ValueError):
        replace(SETTINGS, **changes)


def test_new_fetch_restores_time_basis_and_today_coverage():
    earlier = window()
    shifted = NOW + timedelta(days=1)
    assert not eligible(earlier, now=shifted, mono=101.0)
    fresh = window(
        fetched_at=shifted,
        dates=tuple(shifted.date() + timedelta(days=i) for i in range(5)),
    )
    assert evaluate_weather(
        SETTINGS, WeatherObservation(fresh, 101.0, True, "success"), shifted, 101.0
    ).eligible


@pytest.mark.parametrize("mono", [True, float("nan"), float("inf")])
def test_invalid_clock_never_qualifies(mono):
    assert not eligible(mono=mono)


def test_missing_today_and_date_reversal():
    tomorrow = window(dates=tuple(NOW.date() + timedelta(days=i + 1) for i in range(5)))
    assert not eligible(tomorrow)
    assert not eligible(now=NOW - timedelta(days=1), mono=101.0)


def test_additive_control_mode_and_auto_state():
    from freeze_protect.domain.models import (
        ControllerState,
        ControlMode,
        parse_control_mode,
    )

    assert parse_control_mode("weather_assisted") is ControlMode.WEATHER_ASSISTED
    assert ControllerState.AUTO_SUPPLY.value == "AUTO_SUPPLY"
    assert parse_control_mode("automatic") is ControlMode.AUTOMATIC


def test_oversized_integer_is_rejected_as_invalid_model_value():
    with pytest.raises(ValueError):
        replace(SETTINGS, latitude=10**400)
