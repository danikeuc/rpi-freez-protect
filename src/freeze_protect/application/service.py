from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from freeze_protect.application.ports import (
    AdapterError,
    EventStore,
    ForecastSource,
    RelayDriver,
    TemperatureSource,
)
from freeze_protect.domain.models import (
    AuditEvent,
    ControllerState,
    Decision,
    ForecastSnapshot,
    RelayCommand,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)
from freeze_protect.domain.policy import evaluate


class ControlService:
    """Coordinates pure policy decisions with replaceable local adapters."""

    def __init__(
        self,
        *,
        temperature_source: TemperatureSource,
        forecast_source: ForecastSource,
        relay_driver: RelayDriver,
        event_store: EventStore,
        settings: SafetySettings,
        clock: Callable[[], datetime],
    ) -> None:
        self._temperature_source = temperature_source
        self._forecast_source = forecast_source
        self._relay_driver = relay_driver
        self._event_store = event_store
        self._settings = settings
        self._clock = clock
        self._state = ControllerState.STARTING
        self._last_decision: Decision | None = None
        self._last_reading: TemperatureReading | None = None
        self._last_emitted_non_stop: RelayCommand | None = None
        self._protection_started_at: datetime | None = None

    @property
    def state(self) -> ControllerState:
        return self._state

    @property
    def settings(self) -> SafetySettings:
        return self._settings

    @property
    def last_decision(self) -> Decision | None:
        return self._last_decision

    @property
    def last_reading(self) -> TemperatureReading | None:
        return self._last_reading

    def update_settings(self, settings: SafetySettings) -> None:
        self._settings = settings

    def run_cycle(self) -> Decision:
        try:
            reading = self._temperature_source.read()
        except AdapterError as error:
            return self._fault_from_error("sensor_source_error", error)

        self._last_reading = reading
        try:
            forecast = self._forecast_source.read()
        except AdapterError as error:
            forecast = None
            self._append_event("forecast_source_error", {"error": str(error)})

        decision = self._evaluate_with_dwell(reading, forecast)
        self._state = decision.state
        self._last_decision = decision
        self._append_event(
            "automatic_decision",
            {
                "state": decision.state.value,
                "command": decision.command.value,
                "reason": decision.reason,
            },
        )

        if decision.command is not RelayCommand.STOP:
            self._emit_non_stop(decision)
        return self._last_decision

    def clear_fault(self) -> Decision:
        try:
            reading = self._temperature_source.read()
        except AdapterError as error:
            return self._fault_from_error("sensor_source_error", error)

        self._last_reading = reading
        if reading.health is not SensorHealth.HEALTHY or reading.value_c is None:
            decision = Decision(
                state=ControllerState.FAULT,
                command=RelayCommand.STOP,
                reason="sensor_unhealthy",
            )
            self._state = decision.state
            self._last_decision = decision
            self._append_event(
                "fault_clear_refused",
                {"reason": decision.reason},
            )
            return decision

        decision = Decision(
            state=ControllerState.MONITORING,
            command=RelayCommand.STOP,
            reason="fault_cleared",
        )
        self._state = decision.state
        self._last_decision = decision
        self._protection_started_at = None
        self._append_event("fault_cleared", {"reason": decision.reason})
        return decision

    def manual_command(self, command: RelayCommand) -> Decision:
        if command is RelayCommand.STOP:
            decision = Decision(
                state=ControllerState.MANUAL_LOCK,
                command=RelayCommand.STOP,
                reason="manual_lock",
            )
            self._state = decision.state
            self._last_decision = decision
            self._last_emitted_non_stop = None
            self._append_event(
                "manual_command",
                {"command": command.value, "reason": decision.reason},
            )
            return decision

        try:
            reading = self._temperature_source.read()
        except AdapterError as error:
            return self._fault_from_error("sensor_source_error", error)

        self._last_reading = reading
        if self._state in {ControllerState.STARTING, ControllerState.FAULT}:
            return self._record_manual_refusal("fault_latched", command)
        if self._state is ControllerState.MANUAL_LOCK:
            return self._record_manual_refusal("manual_lock", command)
        if reading.health is not SensorHealth.HEALTHY or reading.value_c is None:
            self._state = ControllerState.FAULT
            return self._record_manual_refusal("sensor_unhealthy", command)

        state = (
            ControllerState.PROTECTING
            if command is RelayCommand.CLOSE_OR_PROTECT
            else ControllerState.MONITORING
        )
        decision = Decision(
            state=state,
            command=command,
            reason=f"manual_{command.value.lower()}",
        )
        self._state = decision.state
        self._last_decision = decision
        if state is ControllerState.PROTECTING:
            self._protection_started_at = self._clock()
        else:
            self._protection_started_at = None
        self._append_event(
            "manual_command",
            {"command": command.value, "reason": decision.reason},
        )
        self._emit_non_stop(decision)
        return self._last_decision

    def _evaluate_with_dwell(
        self,
        reading: TemperatureReading,
        forecast: ForecastSnapshot | None,
    ) -> Decision:
        if (
            self._state is ControllerState.PROTECTING
            and self._protection_started_at is not None
            and reading.health is SensorHealth.HEALTHY
            and reading.value_c is not None
            and reading.value_c > self._settings.protection_threshold_c
            and (self._clock() - self._protection_started_at).total_seconds()
            < self._settings.minimum_protection_dwell_s
        ):
            return Decision(
                state=ControllerState.PROTECTING,
                command=RelayCommand.STOP,
                reason="protection_dwell_active",
            )

        decision = evaluate(
            previous_state=self._state,
            reading=reading,
            forecast=forecast,
            settings=self._settings,
        )
        if (
            decision.state is ControllerState.PROTECTING
            and self._state is not ControllerState.PROTECTING
        ):
            self._protection_started_at = self._clock()
        if decision.state is ControllerState.MONITORING:
            self._protection_started_at = None
        return decision

    def _emit_non_stop(self, decision: Decision) -> None:
        if decision.command is self._last_emitted_non_stop:
            return
        try:
            self._relay_driver.command(decision.command)
        except AdapterError as error:
            self._fault_from_error("relay_driver_error", error)
            return
        self._last_emitted_non_stop = decision.command

    def _record_manual_refusal(
        self,
        reason: str,
        command: RelayCommand,
    ) -> Decision:
        decision = Decision(
            state=self._state,
            command=RelayCommand.STOP,
            reason=reason,
        )
        self._last_decision = decision
        self._append_event(
            "manual_command",
            {"command": command.value, "reason": reason, "accepted": False},
        )
        return decision

    def _fault_from_error(self, event_type: str, error: Exception) -> Decision:
        decision = Decision(
            state=ControllerState.FAULT,
            command=RelayCommand.STOP,
            reason=event_type,
        )
        self._state = decision.state
        self._last_decision = decision
        self._append_event(event_type, {"error": str(error)})
        return decision

    def _append_event(self, event_type: str, payload: dict[str, object]) -> None:
        self._event_store.append(
            AuditEvent(
                id=str(uuid4()),
                occurred_at=self._clock(),
                event_type=event_type,
                payload=payload,
            )
        )
