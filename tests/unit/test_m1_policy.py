from datetime import UTC, date, datetime, timedelta

from freeze_protect.domain.models import (
    ActuatorCommand,
    ControllerState,
    ForecastSnapshot,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)
from freeze_protect.domain.policy import evaluate_automatic

NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)
DATES = tuple(date(2026, 9, 11) + timedelta(days=offset) for offset in range(7))


def settings(**changes: object) -> SafetySettings:
    values: dict[str, object] = {
        "latitude": 46.5547,
        "longitude": 15.6459,
        "timezone": "Europe/Ljubljana",
        "sensor_commissioned": True,
    }
    values.update(changes)
    return SafetySettings(**values)


def healthy_reading(value_c: float = 8.0) -> TemperatureReading:
    return TemperatureReading(value_c, NOW, SensorHealth.HEALTHY)


def eligible_forecast(minima: tuple[float, ...] = (6.0,) * 7) -> ForecastSnapshot:
    return ForecastSnapshot(
        dates=DATES,
        daily_minima_c=minima,
        source_generated_at=NOW,
        fetched_at=NOW,
        latitude=46.5547,
        longitude=15.6459,
    )


def test_uncommissioned_sensor_is_always_frost_protection() -> None:
    decision = evaluate_automatic(
        reading=healthy_reading(),
        forecast=eligible_forecast(),
        settings=settings(sensor_commissioned=False),
        now=NOW,
    )

    assert (decision.state, decision.command, decision.reason) == (
        ControllerState.FROST_PROTECTION,
        ActuatorCommand.DRAIN,
        "sensor_pending",
    )


def test_equal_forecast_threshold_is_not_normal() -> None:
    decision = evaluate_automatic(
        reading=healthy_reading(),
        forecast=eligible_forecast((6.0,) * 6 + (5.0,)),
        settings=settings(),
        now=NOW,
    )

    assert (decision.state, decision.command, decision.reason) == (
        ControllerState.FROST_PROTECTION,
        ActuatorCommand.DRAIN,
        "forecast_not_eligible",
    )


def test_normal_requires_commissioned_healthy_warm_pipe_and_fresh_forecast() -> None:
    decision = evaluate_automatic(
        reading=healthy_reading(7.1),
        forecast=eligible_forecast(),
        settings=settings(),
        now=NOW,
    )

    assert (decision.state, decision.command, decision.reason) == (
        ControllerState.NORMAL,
        ActuatorCommand.SUPPLY,
        "automatic_normal",
    )


def test_unhealthy_commissioned_sensor_remains_in_safe_drain_state() -> None:
    decision = evaluate_automatic(
        reading=TemperatureReading(None, NOW, SensorHealth.STALE),
        forecast=eligible_forecast(),
        settings=settings(),
        now=NOW,
    )

    assert (decision.state, decision.command, decision.reason) == (
        ControllerState.FROST_PROTECTION,
        ActuatorCommand.DRAIN,
        "sensor_unhealthy",
    )
