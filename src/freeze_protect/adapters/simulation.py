from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.models import (
    ActuatorCommand,
    ActuatorReceipt,
    AuditEvent,
    ForecastSnapshot,
    SafetySettings,
    TemperatureReading,
)


class SimulatedTemperatureSource:
    def __init__(self, reading: TemperatureReading) -> None:
        self._reading = reading

    def read(self) -> TemperatureReading:
        return self._reading

    def set(self, reading: TemperatureReading) -> None:
        self._reading = reading


class SimulatedForecastStore:
    def __init__(self, snapshot: ForecastSnapshot | None = None) -> None:
        self._snapshot = snapshot

    def load(self) -> ForecastSnapshot | None:
        return self._snapshot

    def save(self, snapshot: ForecastSnapshot) -> None:
        self._snapshot = snapshot


class SimulatedForecastClient:
    def __init__(self, snapshot: ForecastSnapshot | None = None) -> None:
        self._snapshot = snapshot
        self.calls: list[SafetySettings] = []

    def fetch(self, settings: SafetySettings, now: datetime) -> ForecastSnapshot:
        self.calls.append(settings)
        if self._snapshot is None:
            raise AdapterError("simulated forecast client has no forecast")
        return self._snapshot

    def set(self, snapshot: ForecastSnapshot | None) -> None:
        self._snapshot = snapshot


class SimulatedActuatorDriver:
    def __init__(self, fail_for: set[ActuatorCommand] | None = None) -> None:
        self.commands: list[ActuatorCommand] = []
        self._fail_for = fail_for or set()

    def command(self, command: ActuatorCommand) -> ActuatorReceipt:
        if command in self._fail_for:
            raise AdapterError(f"simulated actuator rejected {command.value}")
        self.commands.append(command)
        level = 0 if command is ActuatorCommand.SUPPLY else 1
        return ActuatorReceipt(
            command=command,
            request_id=str(uuid4()),
            gpio_26=level,
            gpio_20=level,
            flow_revision="simulation",
        )


class InMemoryEventStore:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)
