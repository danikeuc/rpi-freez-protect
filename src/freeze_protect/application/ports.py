from datetime import datetime
from typing import Protocol

from freeze_protect.domain.models import (
    ActuatorCommand,
    ActuatorReceipt,
    AuditEvent,
    ForecastSnapshot,
    SafetySettings,
    TemperatureReading,
)


class AdapterError(RuntimeError):
    """A recoverable failure from a hardware or external-service adapter."""


class TemperatureSource(Protocol):
    def read(self) -> TemperatureReading: ...


class ForecastStore(Protocol):
    def load(self) -> ForecastSnapshot | None: ...

    def save(self, snapshot: ForecastSnapshot) -> None: ...


class ForecastClient(Protocol):
    def fetch(self, settings: SafetySettings, now: datetime) -> ForecastSnapshot: ...


class ActuatorDriver(Protocol):
    def command(self, command: ActuatorCommand) -> ActuatorReceipt: ...


class EventStore(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class SettingsStore(Protocol):
    def load(self) -> SafetySettings: ...

    def save(self, settings: SafetySettings) -> SafetySettings: ...
