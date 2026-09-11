from freeze_protect.domain.models import (
    ControllerState,
    Decision,
    ForecastSnapshot,
    RelayCommand,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)


def evaluate(
    *,
    previous_state: ControllerState,
    reading: TemperatureReading,
    forecast: ForecastSnapshot | None,
    settings: SafetySettings,
) -> Decision:
    """Apply the deterministic safety policy without side effects."""
    if previous_state is ControllerState.MANUAL_LOCK:
        return Decision(
            state=ControllerState.MANUAL_LOCK,
            command=RelayCommand.STOP,
            reason="manual_lock",
        )

    if previous_state in {ControllerState.STARTING, ControllerState.FAULT}:
        return Decision(
            state=ControllerState.FAULT,
            command=RelayCommand.STOP,
            reason="fault_latched",
        )

    if reading.health is not SensorHealth.HEALTHY or reading.value_c is None:
        return Decision(
            state=ControllerState.FAULT,
            command=RelayCommand.STOP,
            reason="sensor_unhealthy",
        )

    if reading.value_c <= settings.protection_threshold_c:
        return Decision(
            state=ControllerState.PROTECTING,
            command=RelayCommand.CLOSE_OR_PROTECT,
            reason="below_protection_threshold",
        )

    if previous_state in {
        ControllerState.PROTECTING,
        ControllerState.RELEASE_PENDING,
    }:
        is_release_eligible = forecast is not None and forecast.has_minima_above(
            settings.release_threshold_c,
            settings.release_days,
        )
        if not is_release_eligible:
            return Decision(
                state=ControllerState.RELEASE_PENDING,
                command=RelayCommand.STOP,
                reason="forecast_not_eligible",
            )
        return Decision(
            state=ControllerState.MONITORING,
            command=RelayCommand.OPEN,
            reason="release_eligible",
        )

    return Decision(
        state=ControllerState.MONITORING,
        command=RelayCommand.STOP,
        reason="monitoring",
    )
