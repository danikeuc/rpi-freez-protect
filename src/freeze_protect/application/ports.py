from datetime import datetime
from typing import Protocol

from freeze_protect.application.weather_worker import WeatherRequest, WeatherResult
from freeze_protect.domain.models import (
    ActuatorCommand,
    ActuatorReceipt,
    AuditEvent,
    ForecastSnapshot,
    SafetySettings,
    SupplyAction,
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
    def command(
        self, command: ActuatorCommand, *, supply_action: SupplyAction | None = None
    ) -> ActuatorReceipt: ...


class EventStore(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class SettingsStore(Protocol):
    def load(self) -> SafetySettings: ...

    def save(self, settings: SafetySettings) -> SafetySettings: ...


class WeatherWorkerPort(Protocol):
    """Nonblocking worker operations; lifecycle ownership remains in the app."""

    def submit(self, request: WeatherRequest) -> bool: ...

    def poll(self) -> WeatherResult | None: ...

    def cancel(self) -> None: ...
