from datetime import UTC, datetime, timedelta

from freeze_protect.adapters.simulation import (
    InMemoryEventStore,
    SimulatedForecastSource,
    SimulatedRelayDriver,
    SimulatedTemperatureSource,
)
from freeze_protect.application.service import ControlService
from freeze_protect.domain.models import (
    ControllerState,
    ForecastSnapshot,
    RelayCommand,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def reading(value_c: float) -> TemperatureReading:
    return TemperatureReading(value_c, datetime.now(UTC), SensorHealth.HEALTHY)


def build_service(
    *,
    reading_c: float = 6.0,
    relay_driver: SimulatedRelayDriver | None = None,
    event_store: InMemoryEventStore | None = None,
    clock: FakeClock | None = None,
    settings: SafetySettings | None = None,
) -> tuple[
    ControlService,
    SimulatedTemperatureSource,
    SimulatedForecastSource,
    SimulatedRelayDriver,
    InMemoryEventStore,
    FakeClock,
]:
    sensor = SimulatedTemperatureSource(reading(reading_c))
    forecasts = SimulatedForecastSource(None)
    relays = relay_driver or SimulatedRelayDriver()
    events = event_store or InMemoryEventStore()
    test_clock = clock or FakeClock(datetime(2026, 9, 11, tzinfo=UTC))
    service = ControlService(
        temperature_source=sensor,
        forecast_source=forecasts,
        relay_driver=relays,
        event_store=events,
        settings=settings or SafetySettings(minimum_protection_dwell_s=60),
        clock=test_clock,
    )
    return service, sensor, forecasts, relays, events, test_clock


def clear_startup_fault(service: ControlService) -> None:
    service.run_cycle()
    decision = service.clear_fault()
    assert decision.state is ControllerState.MONITORING


def test_relay_receives_protection_once_when_state_changes() -> None:
    service, _, _, relays, _, _ = build_service(reading_c=0.5)
    clear_startup_fault(service)

    service.run_cycle()
    service.run_cycle()

    assert relays.commands == [RelayCommand.CLOSE_OR_PROTECT]


def test_each_decision_is_appended_to_audit_log() -> None:
    service, _, _, _, events, _ = build_service(reading_c=0.5)
    clear_startup_fault(service)

    service.run_cycle()

    assert [event.event_type for event in events.events] == [
        "automatic_decision",
        "fault_cleared",
        "automatic_decision",
    ]


def test_manual_stop_enters_lock_and_is_audited() -> None:
    service, _, _, _, events, _ = build_service()
    clear_startup_fault(service)

    decision = service.manual_command(RelayCommand.STOP)

    assert decision.state is ControllerState.MANUAL_LOCK
    assert decision.command is RelayCommand.STOP
    assert events.events[-1].event_type == "manual_command"


def test_relay_driver_error_creates_fault_without_opposite_command() -> None:
    relays = SimulatedRelayDriver(fail_for={RelayCommand.CLOSE_OR_PROTECT})
    service, _, _, _, events, _ = build_service(reading_c=0.5, relay_driver=relays)
    clear_startup_fault(service)

    decision = service.run_cycle()

    assert decision.state is ControllerState.FAULT
    assert relays.commands == []
    assert events.events[-1].event_type == "relay_driver_error"


def test_release_waits_for_the_configured_protection_dwell() -> None:
    service, sensor, forecasts, relays, _, clock = build_service(reading_c=0.5)
    clear_startup_fault(service)
    service.run_cycle()
    sensor.set(reading(6.0))
    forecasts.set(ForecastSnapshot((5.1,) * 7, clock()))

    held = service.run_cycle()
    clock.advance(60)
    released = service.run_cycle()

    assert held.state is ControllerState.PROTECTING
    assert held.command is RelayCommand.STOP
    assert held.reason == "protection_dwell_active"
    assert released.state is ControllerState.MONITORING
    assert released.command is RelayCommand.OPEN
    assert relays.commands == [RelayCommand.CLOSE_OR_PROTECT, RelayCommand.OPEN]
