from datetime import UTC, datetime

import pytest

from freeze_protect.domain.models import (
    ControllerState,
    ForecastSnapshot,
    RelayCommand,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)
from freeze_protect.domain.policy import evaluate

SETTINGS = SafetySettings()


def healthy_reading(value_c: float) -> TemperatureReading:
    return TemperatureReading(
        value_c=value_c,
        observed_at=datetime.now(UTC),
        health=SensorHealth.HEALTHY,
    )


def forecast(minima: tuple[float, ...]) -> ForecastSnapshot:
    return ForecastSnapshot(daily_minima_c=minima, fetched_at=datetime.now(UTC))


def test_low_healthy_temperature_enters_protecting() -> None:
    decision = evaluate(
        previous_state=ControllerState.MONITORING,
        reading=healthy_reading(0.5),
        forecast=None,
        settings=SETTINGS,
    )

    assert decision.state is ControllerState.PROTECTING
    assert decision.command is RelayCommand.CLOSE_OR_PROTECT
    assert decision.reason == "below_protection_threshold"


def test_release_is_blocked_when_forecast_has_a_day_at_threshold() -> None:
    decision = evaluate(
        previous_state=ControllerState.PROTECTING,
        reading=healthy_reading(6.0),
        forecast=forecast((5.1,) * 6 + (5.0,)),
        settings=SETTINGS,
    )

    assert decision.state is ControllerState.RELEASE_PENDING
    assert decision.command is RelayCommand.STOP
    assert decision.reason == "forecast_not_eligible"


@pytest.mark.parametrize(
    "health",
    [SensorHealth.STALE, SensorHealth.INVALID, SensorHealth.CALIBRATION_REQUIRED],
)
def test_unhealthy_sensor_latches_a_fault(health: SensorHealth) -> None:
    decision = evaluate(
        previous_state=ControllerState.MONITORING,
        reading=TemperatureReading(None, datetime.now(UTC), health),
        forecast=None,
        settings=SETTINGS,
    )

    assert decision.state is ControllerState.FAULT
    assert decision.command is RelayCommand.STOP
    assert decision.reason == "sensor_unhealthy"


@pytest.mark.parametrize(
    ("previous_state", "expected_state", "reason"),
    [
        (ControllerState.STARTING, ControllerState.FAULT, "fault_latched"),
        (ControllerState.FAULT, ControllerState.FAULT, "fault_latched"),
        (ControllerState.MANUAL_LOCK, ControllerState.MANUAL_LOCK, "manual_lock"),
    ],
)
def test_locked_states_cannot_automate(
    previous_state: ControllerState,
    expected_state: ControllerState,
    reason: str,
) -> None:
    decision = evaluate(
        previous_state=previous_state,
        reading=healthy_reading(0.0),
        forecast=forecast((7.0,) * 7),
        settings=SETTINGS,
    )

    assert decision.state is expected_state
    assert decision.command is RelayCommand.STOP
    assert decision.reason == reason


def test_healthy_protected_system_opens_only_after_eligible_forecast() -> None:
    decision = evaluate(
        previous_state=ControllerState.PROTECTING,
        reading=healthy_reading(6.0),
        forecast=forecast((5.1,) * 7),
        settings=SETTINGS,
    )

    assert decision.state is ControllerState.MONITORING
    assert decision.command is RelayCommand.OPEN
    assert decision.reason == "release_eligible"


def test_monitoring_state_does_not_reissue_an_open_command() -> None:
    decision = evaluate(
        previous_state=ControllerState.MONITORING,
        reading=healthy_reading(6.0),
        forecast=forecast((9.0,) * 7),
        settings=SETTINGS,
    )

    assert decision.state is ControllerState.MONITORING
    assert decision.command is RelayCommand.STOP
    assert decision.reason == "monitoring"
