from freeze_protect.application.ports import AdapterError
from freeze_protect.domain.models import (
    AuditEvent,
    ForecastSnapshot,
    RelayCommand,
    TemperatureReading,
)


class SimulatedTemperatureSource:
    def __init__(self, reading: TemperatureReading) -> None:
        self._reading = reading

    def read(self) -> TemperatureReading:
        return self._reading

    def set(self, reading: TemperatureReading) -> None:
        self._reading = reading


class SimulatedForecastSource:
    def __init__(self, snapshot: ForecastSnapshot | None) -> None:
        self._snapshot = snapshot

    def read(self) -> ForecastSnapshot | None:
        return self._snapshot

    def set(self, snapshot: ForecastSnapshot | None) -> None:
        self._snapshot = snapshot


class SimulatedRelayDriver:
    def __init__(self, fail_for: set[RelayCommand] | None = None) -> None:
        self.commands: list[RelayCommand] = []
        self._fail_for = fail_for or set()

    def command(self, command: RelayCommand) -> None:
        if command in self._fail_for:
            raise AdapterError(f"simulated relay driver rejected {command.value}")
        self.commands.append(command)


class InMemoryEventStore:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)
