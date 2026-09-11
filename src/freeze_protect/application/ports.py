from typing import Protocol

from freeze_protect.domain.models import (
    AuditEvent,
    ForecastSnapshot,
    RelayCommand,
    SafetySettings,
    TemperatureReading,
)


class AdapterError(RuntimeError):
    """A recoverable failure from a sensor, forecast, or relay adapter."""


class TemperatureSource(Protocol):
    def read(self) -> TemperatureReading: ...


class ForecastSource(Protocol):
    def read(self) -> ForecastSnapshot | None: ...


class RelayDriver(Protocol):
    def command(self, command: RelayCommand) -> None: ...


class EventStore(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class SettingsStore(Protocol):
    def load(self) -> SafetySettings: ...

    def save(self, settings: SafetySettings) -> SafetySettings: ...
