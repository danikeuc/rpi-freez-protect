from datetime import UTC, datetime

import pytest

from freeze_protect.domain.models import (
    ForecastSnapshot,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)


def test_release_requires_exactly_configured_forecast_days() -> None:
    snapshot = ForecastSnapshot(
        daily_minima_c=(5.1,) * 7,
        fetched_at=datetime.now(UTC),
    )

    assert snapshot.has_minima_above(5.0, days=7) is True


def test_release_is_ineligible_with_missing_or_equal_forecast_day() -> None:
    too_short = ForecastSnapshot(
        daily_minima_c=(5.1,) * 6,
        fetched_at=datetime.now(UTC),
    )
    at_threshold = ForecastSnapshot(
        daily_minima_c=(5.1,) * 6 + (5.0,),
        fetched_at=datetime.now(UTC),
    )

    assert too_short.has_minima_above(5.0, days=7) is False
    assert at_threshold.has_minima_above(5.0, days=7) is False


def test_settings_reject_non_positive_release_days() -> None:
    with pytest.raises(ValueError, match="release_days"):
        SafetySettings(release_days=0)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sensor_stale_after_s", 0, "sensor_stale_after_s"),
        ("minimum_protection_dwell_s", 0, "minimum_protection_dwell_s"),
        ("settings_version", 0, "settings_version"),
    ],
)
def test_settings_reject_non_positive_values(
    field: str, value: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        SafetySettings(**{field: value})


def test_settings_require_release_threshold_above_protection_threshold() -> None:
    with pytest.raises(ValueError, match="release_threshold_c"):
        SafetySettings(protection_threshold_c=5.0, release_threshold_c=5.0)


def test_unhealthy_reading_does_not_require_a_temperature_value() -> None:
    reading = TemperatureReading(
        value_c=None,
        observed_at=datetime.now(UTC),
        health=SensorHealth.STALE,
    )

    assert reading.value_c is None
    assert reading.health is SensorHealth.STALE
