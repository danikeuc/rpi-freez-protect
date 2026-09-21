from datetime import datetime

from freeze_protect.domain.models import (
    ActuatorCommand,
    ControllerState,
    Decision,
    ForecastSnapshot,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)


def evaluate_automatic(
    *,
    reading: TemperatureReading,
    forecast: ForecastSnapshot | None,
    settings: SafetySettings,
    now: datetime,
) -> Decision:
    """Evaluate the automatic path; manual timed showers are handled separately."""
    if not settings.sensor_commissioned:
        return Decision(
            state=ControllerState.FROST_PROTECTION,
            command=ActuatorCommand.DRAIN,
            reason="sensor_pending",
        )
    if reading.health is not SensorHealth.HEALTHY or reading.value_c is None:
        return Decision(
            state=ControllerState.FROST_PROTECTION,
            command=ActuatorCommand.DRAIN,
            reason="sensor_unhealthy",
        )
    if reading.value_c <= settings.protection_threshold_c:
        return Decision(
            state=ControllerState.FROST_PROTECTION,
            command=ActuatorCommand.DRAIN,
            reason="pipe_below_protection_threshold",
        )
    if reading.value_c <= settings.release_threshold_c:
        return Decision(
            state=ControllerState.FROST_PROTECTION,
            command=ActuatorCommand.DRAIN,
            reason="pipe_not_above_release_threshold",
        )
    if forecast is None or not forecast.is_eligible(settings, now):
        return Decision(
            state=ControllerState.FROST_PROTECTION,
            command=ActuatorCommand.DRAIN,
            reason="forecast_not_eligible",
        )
    return Decision(
        state=ControllerState.NORMAL,
        command=ActuatorCommand.SUPPLY,
        reason="automatic_normal",
    )
