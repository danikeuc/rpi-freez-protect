from datetime import UTC, date, datetime, timedelta

from freeze_protect.adapters.simulation import (
    InMemoryEventStore,
    SimulatedActuatorDriver,
    SimulatedForecastClient,
    SimulatedForecastStore,
    SimulatedTemperatureSource,
)
from freeze_protect.application.ports import AdapterError
from freeze_protect.application.service import ControlService
from freeze_protect.domain.models import (
    ActuatorCommand,
    ControllerState,
    ForecastSnapshot,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)


class FailingEventStore:
    def append(self, _event: object) -> None:
        raise OSError("disk is read-only")


class RetryOnceDrainDriver(SimulatedActuatorDriver):
    def __init__(self) -> None:
        super().__init__()
        self.attempts: list[ActuatorCommand] = []

    def command(self, command: ActuatorCommand):  # type: ignore[no-untyped-def]
        self.attempts.append(command)
        if command is ActuatorCommand.DRAIN and len(self.attempts) == 1:
            raise AdapterError("first drain attempt failed")
        return super().command(command)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class FakeMonotonic:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += seconds


NOW = datetime(2026, 9, 11, 12, tzinfo=UTC)


def build_service(
    *,
    sensor: TemperatureReading | None = None,
    relay: SimulatedActuatorDriver | None = None,
    settings: SafetySettings | None = None,
    event_store: InMemoryEventStore | FailingEventStore | None = None,
    monotonic_clock: FakeMonotonic | None = None,
) -> tuple[ControlService, SimulatedActuatorDriver, FakeClock]:
    clock = FakeClock(NOW)
    elapsed = monotonic_clock or FakeMonotonic()
    driver = relay or SimulatedActuatorDriver()
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            sensor
            or TemperatureReading(None, NOW, SensorHealth.CALIBRATION_REQUIRED)
        ),
        forecast_store=SimulatedForecastStore(),
        forecast_client=SimulatedForecastClient(),
        actuator_driver=driver,
        event_store=event_store or InMemoryEventStore(),
        settings=settings or SafetySettings(),
        clock=clock,
        monotonic_clock=elapsed,
    )
    return service, driver, clock


def test_startup_always_issues_drain_before_status_becomes_available() -> None:
    service, relay, _ = build_service()

    decision = service.startup()

    assert relay.commands == [ActuatorCommand.DRAIN]
    assert decision.state is ControllerState.FROST_PROTECTION
    assert service.status().state is ControllerState.FROST_PROTECTION
    assert service.status().reason == "sensor_pending"


def test_timed_shower_expires_to_drain_and_never_exceeds_maximum() -> None:
    elapsed = FakeMonotonic()
    service, relay, clock = build_service(monotonic_clock=elapsed)
    service.startup()

    started = service.start_timed_shower()
    clock.advance(601)
    elapsed.advance(601)
    expired = service.run_cycle()

    assert started.state is ControllerState.TIMED_SHOWER
    assert expired.state is ControllerState.FROST_PROTECTION
    assert expired.command is ActuatorCommand.DRAIN
    assert relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.DRAIN,
    ]


def test_repeated_timed_shower_requests_do_not_extend_the_hard_deadline() -> None:
    clock = FakeClock(NOW)
    elapsed = FakeMonotonic()
    relay = SimulatedActuatorDriver()
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            TemperatureReading(None, NOW, SensorHealth.CALIBRATION_REQUIRED)
        ),
        forecast_store=SimulatedForecastStore(),
        forecast_client=SimulatedForecastClient(),
        actuator_driver=relay,
        event_store=InMemoryEventStore(),
        settings=SafetySettings(timed_shower_default_s=600, timed_shower_max_s=1800),
        clock=clock,
        monotonic_clock=elapsed,
    )
    service.startup()

    service.start_timed_shower()
    clock.advance(500)
    elapsed.advance(500)
    repeated = service.start_timed_shower()
    clock.advance(101)
    elapsed.advance(101)
    expired = service.run_cycle()

    assert repeated.reason == "timed_shower_active"
    assert expired.reason == "timed_shower_expired"
    assert relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.DRAIN,
    ]


def test_timed_shower_reports_its_exact_monotonic_wake_deadline() -> None:
    elapsed = FakeMonotonic()
    service, _, _ = build_service(monotonic_clock=elapsed)
    service.startup()
    service.start_timed_shower()

    elapsed.advance(599)
    before_expiry = service.seconds_until_timed_shower_expiry()
    elapsed.advance(1)
    at_expiry = service.seconds_until_timed_shower_expiry()

    assert before_expiry == 1
    assert at_expiry == 0


def test_decommissioning_sensor_immediately_drains_an_active_normal_state() -> None:
    clock = FakeClock(NOW)
    relay = SimulatedActuatorDriver()
    forecast = ForecastSnapshot(
        dates=tuple(date(2026, 9, 11) + timedelta(days=index) for index in range(7)),
        daily_minima_c=(8.0,) * 7,
        source_generated_at=None,
        fetched_at=NOW,
        latitude=46.5547,
        longitude=15.6459,
    )
    commissioned = SafetySettings(
        latitude=46.5547,
        longitude=15.6459,
        sensor_commissioned=True,
    )
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            TemperatureReading(10.0, NOW, SensorHealth.HEALTHY)
        ),
        forecast_store=SimulatedForecastStore(forecast),
        forecast_client=SimulatedForecastClient(),
        actuator_driver=relay,
        event_store=InMemoryEventStore(),
        settings=commissioned,
        clock=clock,
    )
    service.startup()

    updated = service.update_settings(
        SafetySettings(
            latitude=46.5547,
            longitude=15.6459,
            sensor_commissioned=False,
            settings_version=2,
        )
    )

    assert updated.state is ControllerState.FROST_PROTECTION
    assert updated.reason == "sensor_pending"
    assert relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.DRAIN,
    ]


def test_audit_persistence_failure_latches_fault_and_reasserts_drain() -> None:
    relay = SimulatedActuatorDriver()
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            TemperatureReading(None, NOW, SensorHealth.CALIBRATION_REQUIRED)
        ),
        forecast_store=SimulatedForecastStore(),
        forecast_client=SimulatedForecastClient(),
        actuator_driver=relay,
        event_store=FailingEventStore(),
        settings=SafetySettings(),
        clock=FakeClock(NOW),
    )

    decision = service.startup()

    assert decision.state is ControllerState.FAULT
    assert decision.reason == "persistence_error"
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.DRAIN]


def test_persistence_fault_reason_is_not_overwritten_by_a_following_relay_fault() -> None:
    service, _, _ = build_service(
        relay=SimulatedActuatorDriver(fail_for={ActuatorCommand.DRAIN}),
        event_store=FailingEventStore(),
    )

    decision = service.startup()

    assert decision.state is ControllerState.FAULT
    assert decision.reason == "persistence_error"


def test_drain_retries_exactly_once_before_continuing() -> None:
    relay = RetryOnceDrainDriver()
    service, _, _ = build_service(relay=relay)

    decision = service.startup()

    assert decision.state is ControllerState.FROST_PROTECTION
    assert relay.attempts == [ActuatorCommand.DRAIN, ActuatorCommand.DRAIN]
    assert relay.commands == [ActuatorCommand.DRAIN]


def test_supply_failure_attempts_drain_then_latches_fault() -> None:
    service, relay, _ = build_service(
        relay=SimulatedActuatorDriver(fail_for={ActuatorCommand.SUPPLY})
    )
    service.startup()

    decision = service.start_timed_shower()

    assert decision.state is ControllerState.FAULT
    assert decision.command is ActuatorCommand.DRAIN
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.DRAIN]


def test_refresh_forecast_persists_only_a_valid_snapshot() -> None:
    clock = FakeClock(NOW)
    snapshot = ForecastSnapshot(
        dates=tuple(date(2026, 9, 11) + timedelta(days=index) for index in range(7)),
        daily_minima_c=(6.0,) * 7,
        source_generated_at=None,
        fetched_at=NOW,
        latitude=46.5547,
        longitude=15.6459,
    )
    cache = SimulatedForecastStore()
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            TemperatureReading(None, NOW, SensorHealth.CALIBRATION_REQUIRED)
        ),
        forecast_store=cache,
        forecast_client=SimulatedForecastClient(snapshot),
        actuator_driver=SimulatedActuatorDriver(),
        event_store=InMemoryEventStore(),
        settings=SafetySettings(latitude=46.5547, longitude=15.6459),
        clock=clock,
    )

    service.refresh_forecast()

    assert cache.load() == snapshot
