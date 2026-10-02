from datetime import UTC, date, datetime, timedelta

import pytest

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
    ControlMode,
    ForecastSnapshot,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
    parse_control_mode,
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
    mode: ControlMode = ControlMode.SAFE_DRAIN,
) -> tuple[ControlService, SimulatedActuatorDriver, FakeClock]:
    clock = FakeClock(NOW)
    elapsed = monotonic_clock or FakeMonotonic()
    driver = relay or SimulatedActuatorDriver()
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            sensor or TemperatureReading(None, NOW, SensorHealth.CALIBRATION_REQUIRED)
        ),
        forecast_store=SimulatedForecastStore(),
        forecast_client=SimulatedForecastClient(),
        actuator_driver=driver,
        event_store=event_store or InMemoryEventStore(),
        settings=settings or SafetySettings(),
        clock=clock,
        monotonic_clock=elapsed,
        mode=mode,
    )
    return service, driver, clock


def test_startup_always_issues_drain_before_status_becomes_available() -> None:
    service, relay, _ = build_service()

    decision = service.startup()

    assert relay.commands == [ActuatorCommand.DRAIN]
    assert decision.state is ControllerState.SAFE_DRAIN
    assert service.status().state is ControllerState.SAFE_DRAIN


def test_mode_parser_fails_closed() -> None:
    assert parse_control_mode(None) is ControlMode.SAFE_DRAIN
    assert parse_control_mode("invalid") is ControlMode.SAFE_DRAIN
    assert parse_control_mode("manual_timed") is ControlMode.MANUAL_TIMED
    assert parse_control_mode("automatic") is ControlMode.AUTOMATIC


def test_manual_startup_and_idle_cycle_never_read_inputs_or_supply() -> None:
    service, relay, _ = build_service(mode=ControlMode.MANUAL_TIMED)

    def forbidden() -> None:
        raise AssertionError("input port was read")

    service._temperature_source.read = forbidden  # type: ignore[method-assign]
    service._forecast_store.load = forbidden  # type: ignore[method-assign]
    service._forecast_client.fetch = forbidden  # type: ignore[method-assign]

    assert service.startup().state is ControllerState.MANUAL_DRAIN
    assert service.run_cycle().state is ControllerState.MANUAL_DRAIN
    assert service.status().state is ControllerState.MANUAL_DRAIN
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.DRAIN]


def test_safe_startup_and_idle_cycle_never_read_inputs_or_supply() -> None:
    service, relay, _ = build_service()

    def forbidden() -> None:
        raise AssertionError("input port was read")

    service._temperature_source.read = forbidden  # type: ignore[method-assign]
    service._forecast_store.load = forbidden  # type: ignore[method-assign]
    service._forecast_client.fetch = forbidden  # type: ignore[method-assign]

    assert service.startup().state is ControllerState.SAFE_DRAIN
    assert service.run_cycle().state is ControllerState.SAFE_DRAIN
    assert service.status().state is ControllerState.SAFE_DRAIN
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.DRAIN]


def test_warm_forecast_cannot_supply_in_manual_mode() -> None:
    forecast = ForecastSnapshot(
        dates=tuple(date(2026, 9, 11) + timedelta(days=index) for index in range(7)),
        daily_minima_c=(10.0,) * 7,
        source_generated_at=None,
        fetched_at=NOW,
        latitude=46.5547,
        longitude=15.6459,
    )
    relay = SimulatedActuatorDriver()
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            TemperatureReading(10.0, NOW, SensorHealth.HEALTHY)
        ),
        forecast_store=SimulatedForecastStore(forecast),
        forecast_client=SimulatedForecastClient(forecast),
        actuator_driver=relay,
        event_store=InMemoryEventStore(),
        settings=SafetySettings(
            latitude=46.5547, longitude=15.6459, sensor_commissioned=True
        ),
        clock=FakeClock(NOW),
        mode=ControlMode.MANUAL_TIMED,
    )

    assert service.startup().state is ControllerState.MANUAL_DRAIN
    assert service.run_cycle().state is ControllerState.MANUAL_DRAIN
    assert (
        service.update_settings(service.settings).state is ControllerState.MANUAL_DRAIN
    )
    assert service.refresh_forecast() is None
    assert service.status().forecast is None
    assert ActuatorCommand.SUPPLY not in relay.commands


def test_timed_shower_expires_to_drain_and_never_exceeds_maximum() -> None:
    elapsed = FakeMonotonic()
    service, relay, clock = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()

    started = service.start_timed_shower()
    clock.advance(601)
    elapsed.advance(601)
    expired = service.run_cycle()

    assert started.state is ControllerState.TIMED_SHOWER
    assert expired.state is ControllerState.MANUAL_DRAIN
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
        mode=ControlMode.MANUAL_TIMED,
    )
    service.startup()

    service.start_timed_shower()
    assert service.mode is ControlMode.MANUAL_TIMED
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
    service, _, _ = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()
    service.start_timed_shower()

    elapsed.advance(599)
    before_expiry = service.seconds_until_timed_shower_expiry()
    elapsed.advance(1)
    at_expiry = service.seconds_until_timed_shower_expiry()

    assert before_expiry == 1
    assert at_expiry == 0


def test_active_timed_shower_renews_the_supply_lease_each_cycle() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()
    service.start_timed_shower()
    elapsed.advance(30)

    decision = service.run_cycle()

    assert decision.reason == "timed_shower_active"
    assert relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.SUPPLY,
    ]


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
        mode=ControlMode.AUTOMATIC,
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


def test_persistence_fault_reason_is_not_overwritten_by_a_following_relay_fault() -> (
    None
):
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

    assert decision.state is ControllerState.SAFE_DRAIN
    assert relay.attempts == [ActuatorCommand.DRAIN, ActuatorCommand.DRAIN]
    assert relay.commands == [ActuatorCommand.DRAIN]


def test_supply_failure_attempts_drain_then_latches_fault() -> None:
    service, relay, _ = build_service(
        relay=SimulatedActuatorDriver(fail_for={ActuatorCommand.SUPPLY}),
        mode=ControlMode.MANUAL_TIMED,
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
        mode=ControlMode.AUTOMATIC,
    )

    service.refresh_forecast()

    assert cache.load() == snapshot


def test_manual_interval_is_fixed_at_600_seconds_despite_admin_default() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        settings=SafetySettings(timed_shower_default_s=120, timed_shower_max_s=900),
        monotonic_clock=elapsed,
        mode=ControlMode.MANUAL_TIMED,
    )
    assert service.startup().state is ControllerState.MANUAL_DRAIN

    started = service.start_timed_shower()
    elapsed.advance(500)

    assert started.command is ActuatorCommand.SUPPLY
    assert service.seconds_until_timed_shower_expiry() == 100
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.SUPPLY]


@pytest.mark.parametrize("seconds", range(60, 601, 60))
def test_manual_duration_accepts_whole_minutes(seconds: int) -> None:
    service, relay, _ = build_service(mode=ControlMode.MANUAL_TIMED)
    service.startup()

    decision = service.start_timed_shower(seconds)

    assert decision.command is ActuatorCommand.SUPPLY
    assert service.status().timed_shower_deadline == NOW + timedelta(seconds=seconds)
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.SUPPLY]


@pytest.mark.parametrize("duration", [True, 60.0, "60", 0, 59, 61, 601])
def test_manual_duration_rejects_invalid_values(duration: object) -> None:
    service, relay, _ = build_service(mode=ControlMode.MANUAL_TIMED)
    service.startup()

    with pytest.raises(ValueError):
        service.start_timed_shower(duration)  # type: ignore[arg-type]

    assert relay.commands == [ActuatorCommand.DRAIN]
    assert service.status().timed_shower_deadline is None


@pytest.mark.parametrize("mode", [ControlMode.SAFE_DRAIN, ControlMode.AUTOMATIC])
def test_explicit_duration_rejected_outside_manual(mode: ControlMode) -> None:
    service, relay, _ = build_service(mode=mode)
    service.startup()
    before = list(relay.commands)

    decision = service.start_timed_shower(60)

    assert decision.command is ActuatorCommand.DRAIN
    assert decision.reason == "manual_duration_requires_manual_mode"
    assert relay.commands == before


def test_explicit_duration_rejected_during_active_automatic_shower() -> None:
    service, relay, _ = build_service(mode=ControlMode.AUTOMATIC)
    service.startup()
    assert service.start_timed_shower().command is ActuatorCommand.SUPPLY
    original_deadline = service.status().timed_shower_deadline
    before = list(relay.commands)

    rejected = service.start_timed_shower(60)

    assert rejected.state is ControllerState.TIMED_SHOWER
    assert rejected.command is ActuatorCommand.SUPPLY
    assert rejected.reason == "manual_duration_requires_manual_mode"
    assert service.status().timed_shower_deadline == original_deadline
    assert relay.commands == before


def test_duration_respects_configured_max() -> None:
    service, relay, _ = build_service(
        mode=ControlMode.MANUAL_TIMED,
        settings=SafetySettings(timed_shower_default_s=120, timed_shower_max_s=300),
    )
    service.startup()

    decision = service.start_timed_shower(360)

    assert decision.reason == "manual_duration_exceeds_settings_limit"
    assert relay.commands == [ActuatorCommand.DRAIN]
    assert service.status().timed_shower_deadline is None


def test_duration_retry_does_not_extend_deadline() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        mode=ControlMode.MANUAL_TIMED, monotonic_clock=elapsed
    )
    service.startup()
    service.start_timed_shower(60)
    elapsed.advance(30)

    repeated = service.start_timed_shower(600)

    assert repeated.reason == "timed_shower_active"
    assert service.status().timed_shower_deadline == NOW + timedelta(seconds=60)
    assert service.seconds_until_timed_shower_expiry() == 30
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.SUPPLY]


def test_short_active_duration_survives_lowered_maximum_above_its_length() -> None:
    service, relay, _ = build_service(mode=ControlMode.MANUAL_TIMED)
    service.startup()
    service.start_timed_shower(60)

    decision = service.update_settings(
        SafetySettings(timed_shower_default_s=120, timed_shower_max_s=120)
    )

    assert decision.command is ActuatorCommand.SUPPLY
    assert service.status().timed_shower_deadline == NOW + timedelta(seconds=60)
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.SUPPLY]


def test_manual_interval_refuses_supply_when_settings_maximum_is_below_600() -> None:
    service, relay, _ = build_service(
        settings=SafetySettings(timed_shower_default_s=120, timed_shower_max_s=500),
        mode=ControlMode.MANUAL_TIMED,
    )
    service.startup()

    decision = service.start_timed_shower()

    assert decision.state is ControllerState.MANUAL_DRAIN
    assert decision.command is ActuatorCommand.DRAIN
    assert decision.reason == "manual_duration_exceeds_settings_limit"
    assert service.seconds_until_timed_shower_expiry() is None
    assert relay.commands == [ActuatorCommand.DRAIN]


def test_safe_mode_refuses_timed_supply_as_unconfigured() -> None:
    service, relay, _ = build_service()
    service.startup()

    decision = service.start_timed_shower()

    assert decision.state is ControllerState.SAFE_DRAIN
    assert decision.command is ActuatorCommand.DRAIN
    assert decision.reason == "operating_mode_not_configured"
    assert ActuatorCommand.SUPPLY not in relay.commands


def test_duplicate_manual_press_at_500_seconds_keeps_original_deadline() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()
    service.start_timed_shower()
    elapsed.advance(500)

    repeated = service.start_timed_shower()

    assert repeated.reason == "timed_shower_active"
    assert service.seconds_until_timed_shower_expiry() == 100
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.SUPPLY]


def test_manual_cycle_renews_before_expiry_and_drains_at_exact_deadline() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()
    service.start_timed_shower()
    elapsed.advance(599)
    active = service.run_cycle()
    elapsed.advance(1)
    expired = service.run_cycle()

    assert active.command is ActuatorCommand.SUPPLY
    assert expired.state is ControllerState.MANUAL_DRAIN
    assert expired.command is ActuatorCommand.DRAIN
    assert service.seconds_until_timed_shower_expiry() is None
    assert relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.DRAIN,
    ]


def test_expired_boundary_press_drains_before_a_later_press_can_restart() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()
    service.start_timed_shower()
    elapsed.advance(600)

    boundary = service.start_timed_shower()
    later = service.start_timed_shower()

    assert boundary.state is ControllerState.MANUAL_DRAIN
    assert boundary.reason == "timed_shower_expired"
    assert later.reason == "timed_shower_started"
    assert service.seconds_until_timed_shower_expiry() == 600
    assert relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
    ]


def test_settings_update_preserves_active_manual_deadline() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()
    service.start_timed_shower()
    elapsed.advance(200)

    updated = service.update_settings(
        SafetySettings(
            timed_shower_default_s=300,
            timed_shower_max_s=900,
            settings_version=2,
        )
    )

    assert updated.command is ActuatorCommand.SUPPLY
    assert service.seconds_until_timed_shower_expiry() == 400
    assert relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.SUPPLY]


def test_lowering_settings_maximum_below_600_drains_active_manual_interval() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()
    service.start_timed_shower()
    elapsed.advance(200)

    decision = service.update_settings(
        SafetySettings(
            timed_shower_default_s=300,
            timed_shower_max_s=500,
            settings_version=2,
        )
    )

    assert decision.state is ControllerState.MANUAL_DRAIN
    assert decision.command is ActuatorCommand.DRAIN
    assert decision.reason == "manual_duration_exceeds_settings_limit"
    assert service.seconds_until_timed_shower_expiry() is None
    assert relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.DRAIN,
    ]


def test_manual_drain_cancels_interval_and_restart_stays_drained() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()
    service.start_timed_shower()

    drained = service.drain()
    restarted = service.startup()

    assert drained.state is ControllerState.MANUAL_DRAIN
    assert restarted.state is ControllerState.MANUAL_DRAIN
    assert service.seconds_until_timed_shower_expiry() is None
    assert relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.DRAIN,
        ActuatorCommand.DRAIN,
    ]


def test_failed_supply_receipt_and_event_persistence_clear_manual_deadlines() -> None:
    supply_failure, failed_relay, _ = build_service(
        relay=SimulatedActuatorDriver(fail_for={ActuatorCommand.SUPPLY}),
        mode=ControlMode.MANUAL_TIMED,
    )
    supply_failure.startup()
    failed = supply_failure.start_timed_shower()

    class FailStartEventStore(InMemoryEventStore):
        def append(self, event: object) -> None:
            if event.event_type == "timed_shower_started":  # type: ignore[attr-defined]
                raise OSError("disk is read-only")
            super().append(event)  # type: ignore[arg-type]

    persistence_failure, persisted_relay, _ = build_service(
        event_store=FailStartEventStore(), mode=ControlMode.MANUAL_TIMED
    )
    persistence_failure.startup()
    faulted = persistence_failure.start_timed_shower()

    assert failed.state is ControllerState.FAULT
    assert supply_failure.seconds_until_timed_shower_expiry() is None
    assert failed_relay.commands == [ActuatorCommand.DRAIN, ActuatorCommand.DRAIN]
    assert faulted.reason == "persistence_error"
    assert persistence_failure.seconds_until_timed_shower_expiry() is None
    assert persisted_relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.DRAIN,
    ]


def test_safe_mode_refusal_preserves_a_failed_drain_receipt_fault() -> None:
    class FailAfterStartupDriver(SimulatedActuatorDriver):
        def command(self, command: ActuatorCommand):  # type: ignore[no-untyped-def]
            if self.commands:
                raise AdapterError("drain receipt unavailable")
            return super().command(command)

    relay = FailAfterStartupDriver()
    service, _, _ = build_service(relay=relay)
    service.startup()

    decision = service.start_timed_shower()

    assert decision.state is ControllerState.FAULT
    assert decision.command is ActuatorCommand.DRAIN
    assert decision.reason == "relay_driver_error"


def test_restart_from_active_manual_supply_drains_and_clears_both_deadlines() -> None:
    elapsed = FakeMonotonic()
    service, relay, _ = build_service(
        monotonic_clock=elapsed, mode=ControlMode.MANUAL_TIMED
    )
    service.startup()
    active = service.start_timed_shower()
    assert active.command is ActuatorCommand.SUPPLY
    assert service.status().timed_shower_deadline is not None
    assert service.seconds_until_timed_shower_expiry() == 600

    restarted = service.startup()

    assert restarted.state is ControllerState.MANUAL_DRAIN
    assert restarted.command is ActuatorCommand.DRAIN
    assert service.status().timed_shower_deadline is None
    assert service.seconds_until_timed_shower_expiry() is None
    assert relay.commands == [
        ActuatorCommand.DRAIN,
        ActuatorCommand.SUPPLY,
        ActuatorCommand.DRAIN,
    ]
