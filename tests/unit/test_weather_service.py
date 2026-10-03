"""Weather control traces use only simulated whole-pair actuator receipts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from freeze_protect.adapters.simulation import (
    InMemoryEventStore,
    SimulatedActuatorDriver,
    SimulatedForecastClient,
    SimulatedForecastStore,
    SimulatedTemperatureSource,
)
from freeze_protect.application.service import ControlService
from freeze_protect.application.weather_control import WeatherCoordinator
from freeze_protect.application.weather_worker import WeatherResult
from freeze_protect.domain.models import (
    ActuatorCommand as Command,
)
from freeze_protect.domain.models import (
    ControllerState as State,
)
from freeze_protect.domain.models import (
    ControlMode,
    SafetySettings,
    SensorHealth,
    SupplyAction,
    TemperatureReading,
)
from freeze_protect.domain.weather import WeatherSettings, WeatherWindow
from freeze_protect.persistence.weather import SQLiteWeatherStore, WeatherStateError


class FakeWorker:
    def __init__(self):
        self.requests = []
        self.result = None
        self.busy = False
        self.cancelled = 0

    def submit(self, request):
        if self.busy:
            return False
        self.requests.append(request)
        return True

    def poll(self):
        result, self.result = self.result, None
        return result

    def cancel(self):
        self.cancelled += 1
        self.result = None


class Rig:
    def __init__(self, tmp_path, *, settings=None, driver=None):
        self.now = datetime(2026, 10, 3, 10, tzinfo=UTC)
        self.mono = 100.0
        self.store = SQLiteWeatherStore(tmp_path / "weather.db")
        record = self.store.load()
        if settings is None:
            settings = WeatherSettings(True, 46.5, 15.5)
        self.store.compare_and_swap(
            record.control_revision, replace(record, settings=settings)
        )
        self.worker = FakeWorker()
        self.driver = driver or SimulatedActuatorDriver()
        self.coordinator = WeatherCoordinator(
            self.store, self.worker, lambda: self.now, lambda: self.mono
        )
        self.service = self.new_service()

    def new_service(self):
        return ControlService(
            temperature_source=SimulatedTemperatureSource(
                TemperatureReading(None, self.now, SensorHealth.INVALID)
            ),
            forecast_store=SimulatedForecastStore(),
            forecast_client=SimulatedForecastClient(),
            actuator_driver=self.driver,
            event_store=InMemoryEventStore(),
            settings=SafetySettings(),
            clock=lambda: self.now,
            monotonic_clock=lambda: self.mono,
            mode=ControlMode.WEATHER_ASSISTED,
            weather_coordinator=self.coordinator,
            weather_store=self.store,
        )

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.mono += seconds

    def result(self, minimum=5.0, error=None, *, request=None, started=None):
        request = request or self.worker.requests[-1]
        today = request.requested_at.astimezone(
            ZoneInfo(request.settings.timezone)
        ).date()
        window = WeatherWindow(
            tuple(today + timedelta(days=i) for i in range(5)),
            (minimum,) * 5,
            request.requested_at,
            request.settings.latitude,
            request.settings.longitude,
            request.settings.timezone,
            request.settings.revision,
            request.generation,
        )
        self.worker.result = WeatherResult(
            request,
            None if error else window,
            error,
            self.mono if started is None else started,
        )

    def warm(self):
        self.service.startup()
        self.result()
        return self.service.run_cycle()


def test_startup_drain_then_warm_begin_renew_without_revision_churn(tmp_path):
    rig = Rig(tmp_path)
    assert rig.service.startup().command is Command.DRAIN
    assert rig.driver.commands == [Command.DRAIN]
    rig.result()
    assert rig.service.run_cycle().state is State.AUTO_SUPPLY
    revision = rig.store.load().control_revision
    rig.advance(30)
    assert rig.service.run_cycle().state is State.AUTO_SUPPLY
    assert rig.driver.actions == [None, SupplyAction.BEGIN, SupplyAction.RENEW]
    assert rig.store.load().active_marker == "auto"
    assert rig.store.load().control_revision == revision
    assert rig.service.status().remaining_seconds == 0


def test_latest_failure_invalidates_warm_cache_and_drains(tmp_path):
    rig = Rig(tmp_path)
    rig.warm()
    rig.advance(900)
    rig.service.run_cycle()
    rig.result(error="fetch_failed")
    assert rig.service.run_cycle().command is Command.DRAIN
    assert rig.store.load().active_marker is None
    status = rig.service.weather_status()
    assert status.operation == "MANUAL_IDLE"
    assert not status.eligibility.eligible
    assert status.observation.window.fetched_at == rig.worker.requests[0].requested_at
    assert not status.observation.latest_attempt_ok


def test_cold_and_missing_location_allow_deliberate_bounded_shower(tmp_path):
    for name, settings in [("cold", None), ("missing", WeatherSettings(True))]:
        rig = Rig(tmp_path / name, settings=settings)
        rig.service.startup()
        if name == "cold":
            rig.result(4.99)
            assert rig.service.run_cycle().command is Command.DRAIN
        assert rig.service.start_weather_shower(180).state is State.TIMED_SHOWER
        assert rig.service.status().remaining_seconds == 180


@pytest.mark.parametrize("change", ["warm", "cold", "disabled", "location"])
def test_manual_deadline_survives_weather_and_admin_changes(tmp_path, change):
    rig = Rig(tmp_path)
    rig.service.startup()
    rig.service.start_timed_shower(180)
    deadline = rig.service.status().timed_shower_deadline
    rig.advance(60)
    if change in ("warm", "cold"):
        rig.result(10 if change == "warm" else -1, started=100)
    else:
        settings = rig.store.load().settings
        updated = (
            replace(settings, enabled=False)
            if change == "disabled"
            else replace(settings, latitude=47)
        )
        rig.service.update_weather_settings(settings.revision, updated)
    rig.service.run_cycle()
    rig.service.start_weather_shower(600)
    assert rig.service.status().timed_shower_deadline == deadline
    assert rig.service.status().remaining_seconds == 120
    rig.advance(120)
    assert rig.service.run_cycle().command is Command.DRAIN
    assert rig.driver.commands[-1] is Command.DRAIN
    assert rig.store.load().active_marker is None


def test_manual_expiry_drains_before_later_auto_begin(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    rig.service.start_timed_shower(180)
    rig.result()
    rig.service.run_cycle()
    rig.advance(180)
    assert rig.service.run_cycle().command is Command.DRAIN
    assert rig.service.run_cycle().state is State.AUTO_SUPPLY
    assert rig.driver.commands[-2:] == [Command.DRAIN, Command.SUPPLY]
    assert rig.driver.actions[-1] is SupplyAction.BEGIN


def test_stop_persists_before_drain_and_success_cannot_reopen(tmp_path):
    rig = Rig(tmp_path)
    rig.warm()
    original = rig.driver.command

    def checked(command, **kwargs):
        if command is Command.DRAIN:
            assert rig.store.load().user_off
        return original(command, **kwargs)

    rig.driver.command = checked
    assert rig.service.stop_weather_shower().command is Command.DRAIN
    assert rig.service.weather_status().operation == "USER_OFF"
    assert rig.service.start_timed_shower(180).reason == "weather_start_required"
    rig.service.run_cycle()
    assert rig.driver.commands[-1] is Command.DRAIN
    assert rig.service.start_weather_shower(180).state is State.AUTO_SUPPLY


def test_start_write_failure_emits_no_supply(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.service.startup()

    def fail(*args):
        raise WeatherStateError("injected failure")

    monkeypatch.setattr(rig.store, "compare_and_swap", fail)
    assert rig.service.start_weather_shower(180).state is State.FAULT
    assert Command.SUPPLY not in rig.driver.commands


def test_failed_fault_write_retains_marker_and_reboot_inhibits(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.warm()
    original = rig.store.compare_and_swap

    def fail(*args):
        raise WeatherStateError("injected failure")

    monkeypatch.setattr(rig.store, "compare_and_swap", fail)
    assert rig.service.stop_weather_shower().state is State.FAULT
    assert rig.store.load().active_marker == "auto"
    monkeypatch.setattr(rig.store, "compare_and_swap", original)
    rig.coordinator = WeatherCoordinator(
        rig.store, rig.worker, lambda: rig.now, lambda: rig.mono
    )
    restarted = rig.new_service()
    assert restarted.startup().command is Command.DRAIN
    rig.result()
    assert restarted.run_cycle().command is Command.DRAIN
    assert restarted.weather_status().operation == "USER_OFF"


def test_clean_shutdown_requires_new_fetch_but_allows_auto(tmp_path):
    rig = Rig(tmp_path)
    rig.warm()
    rig.service.shutdown()
    assert rig.store.load().active_marker is None
    assert not rig.store.load().user_off
    restarted = rig.new_service()
    assert restarted.startup().command is Command.DRAIN
    rig.result()
    assert restarted.run_cycle().state is State.AUTO_SUPPLY


def test_database_corruption_during_supply_faults_and_drains(tmp_path):
    rig = Rig(tmp_path)
    rig.warm()
    (tmp_path / "weather.db").write_bytes(b"not sqlite")
    assert rig.service.run_cycle().state is State.FAULT
    assert rig.driver.commands[-1] is Command.DRAIN


def test_old_location_result_is_discarded(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    request = rig.worker.requests[-1]
    settings = rig.store.load().settings
    rig.service.update_weather_settings(
        settings.revision, replace(settings, latitude=47)
    )
    rig.result(request=request)
    assert rig.service.run_cycle().command is Command.DRAIN
    rig.result()
    assert rig.service.run_cycle().state is State.AUTO_SUPPLY


def test_clock_invalidity_is_latched_until_fresh_result(tmp_path):
    rig = Rig(tmp_path)
    rig.warm()
    rig.now += timedelta(seconds=31)
    assert rig.service.run_cycle().command is Command.DRAIN
    rig.now -= timedelta(seconds=31)
    assert rig.service.run_cycle().command is Command.DRAIN
    rig.result()  # Request made before the second clock jump is also invalid.
    assert rig.service.run_cycle().command is Command.DRAIN
    rig.result()
    assert rig.service.run_cycle().state is State.AUTO_SUPPLY


def test_request_start_is_freshness_anchor(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    rig.advance(4)
    rig.result(started=100)
    assert rig.service.run_cycle().state is State.AUTO_SUPPLY
    assert rig.coordinator.observation.received_mono == 100


def test_refresh_cadence_enable_and_midnight(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    rig.result()
    rig.service.run_cycle()
    rig.advance(899)
    rig.service.run_cycle()
    assert len(rig.worker.requests) == 1
    rig.advance(1)
    rig.service.run_cycle()
    assert len(rig.worker.requests) == 2
    settings = rig.store.load().settings
    settings = rig.service.update_weather_settings(
        settings.revision, replace(settings, enabled=False)
    )
    rig.service.update_weather_settings(
        settings.revision, replace(settings, enabled=True)
    )
    assert len(rig.worker.requests) == 3
    rig.now = rig.now.replace(hour=23)
    rig.service.run_cycle()
    assert len(rig.worker.requests) == 4


def test_get_status_does_not_begin_or_increment_revision(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    rig.result()
    revision = rig.store.load().control_revision
    assert rig.service.weather_status().operation == "MANUAL_IDLE"
    assert rig.driver.commands == [Command.DRAIN]
    assert rig.store.load().control_revision == revision


def test_startup_drain_failure_faults_and_never_fetches(tmp_path):
    rig = Rig(tmp_path, driver=SimulatedActuatorDriver({Command.DRAIN}))
    assert rig.service.startup().state is State.FAULT
    assert not rig.worker.requests
    assert rig.store.load().fault_inhibited
    assert rig.service.start_weather_shower(180).state is State.FAULT


def test_missing_store_startup_still_drains_then_faults():
    from test_m1_service import build_service

    service, driver, _ = build_service(mode=ControlMode.WEATHER_ASSISTED)
    assert service.startup().state is State.FAULT
    assert driver.commands and set(driver.commands) == {Command.DRAIN}


def test_fault_clear_drains_and_leaves_user_off(tmp_path):
    from freeze_protect.application.ports import AdapterError

    rig = Rig(tmp_path)
    rig.warm()
    original = rig.driver.command

    def reject_renew(command, **kwargs):
        if kwargs.get("supply_action") is SupplyAction.RENEW:
            raise AdapterError("lease rejected")
        return original(command, **kwargs)

    rig.driver.command = reject_renew
    assert rig.service.run_cycle().state is State.FAULT
    assert rig.store.load().active_marker == "auto"
    assert rig.service.clear_fault().command is Command.DRAIN
    assert rig.service.weather_status().operation == "USER_OFF"
    assert not rig.store.load().fault_inhibited
    assert rig.store.load().active_marker is None
    assert rig.service.run_cycle().command is Command.DRAIN


def test_shutdown_after_disk_recovers_must_preserve_local_fault(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.warm()
    original = rig.store.compare_and_swap

    def fail(*args):
        raise WeatherStateError("disk failed")

    monkeypatch.setattr(rig.store, "compare_and_swap", fail)
    rig.service.stop_weather_shower()
    monkeypatch.setattr(rig.store, "compare_and_swap", original)
    rig.service.shutdown()
    assert rig.store.load().fault_inhibited
    assert rig.store.load().user_off
    assert rig.store.load().active_marker is None


def test_legacy_bounded_action_from_auto_confirms_drain_before_new_begin(tmp_path):
    rig = Rig(tmp_path)
    rig.warm()
    assert rig.service.start_timed_shower(180).state is State.TIMED_SHOWER
    assert rig.driver.commands[-2:] == [Command.DRAIN, Command.SUPPLY]
    assert rig.driver.actions[-1] is SupplyAction.BEGIN
    assert rig.store.load().active_marker == "manual"


def test_active_marker_is_durable_before_begin(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    original = rig.driver.command

    def checked(command, **kwargs):
        if command is Command.SUPPLY:
            assert rig.store.load().active_marker == "manual"
        return original(command, **kwargs)

    rig.driver.command = checked
    rig.service.start_weather_shower(180)


def test_failed_settings_write_drains_active_supply(tmp_path, monkeypatch):
    rig = Rig(tmp_path)
    rig.warm()
    settings = rig.store.load().settings

    def fail(*args):
        raise WeatherStateError("disk failed")

    monkeypatch.setattr(rig.store, "compare_and_swap", fail)
    with pytest.raises(WeatherStateError):
        rig.service.update_weather_settings(
            settings.revision, replace(settings, enabled=False)
        )
    assert rig.service.status().state is State.FAULT
    assert rig.driver.commands[-1] is Command.DRAIN
    assert rig.store.load().active_marker == "auto"


def test_stale_settings_and_action_revisions_do_not_change_control(tmp_path):
    from freeze_protect.persistence.weather import WeatherRevisionConflict

    rig = Rig(tmp_path)
    rig.warm()
    record = rig.store.load()
    with pytest.raises(WeatherRevisionConflict):
        rig.service.update_weather_settings(
            record.settings.revision - 1, record.settings
        )
    with (
        pytest.raises(WeatherRevisionConflict),
        rig.service.weather_action_guard(record.control_revision - 1),
    ):
        rig.service.stop_weather_shower()
    assert rig.store.load() == record
    assert rig.service.status().state is State.AUTO_SUPPLY


def test_action_guard_serializes_settings_edit(tmp_path):
    from threading import Event, Thread

    rig = Rig(tmp_path)
    rig.service.startup()
    record = rig.store.load()
    entered, completed = Event(), Event()

    def update():
        entered.set()
        rig.service.update_weather_settings(
            record.settings.revision, replace(record.settings, enabled=False)
        )
        completed.set()

    with rig.service.weather_action_guard(record.control_revision):
        thread = Thread(target=update)
        thread.start()
        assert entered.wait(1)
        assert not completed.wait(0.05)
        assert rig.service.start_weather_shower(180).state is State.TIMED_SHOWER
    thread.join(1)
    assert completed.is_set()
    assert rig.service.status().remaining_seconds == 180


@pytest.mark.parametrize("failure", ["raise", "malformed_pair"])
def test_unexpected_or_malformed_driver_reply_faults_and_drains(tmp_path, failure):
    from types import SimpleNamespace

    rig = Rig(tmp_path)
    rig.service.startup()
    original = rig.driver.command

    def broken(command, **kwargs):
        if command is Command.SUPPLY:
            if failure == "raise":
                raise RuntimeError("injected driver failure")
            return SimpleNamespace(
                command=command,
                protocol_version=2,
                supply_action=kwargs["supply_action"],
                gpio_26=0,
                gpio_20=1,
            )
        return original(command, **kwargs)

    rig.driver.command = broken
    assert rig.service.start_weather_shower(180).state is State.FAULT
    assert rig.driver.commands[-1] is Command.DRAIN
    assert rig.store.load().fault_inhibited


def test_status_clock_fault_cannot_be_erased_by_clock_restoration(tmp_path):
    rig = Rig(tmp_path)
    rig.warm()
    rig.now += timedelta(seconds=31)
    assert rig.service.weather_status().eligibility.reason == "time_basis_invalid"
    rig.now -= timedelta(seconds=31)
    assert rig.service.run_cycle().command is Command.DRAIN


def test_operator_drain_remains_available_with_unreadable_storage(tmp_path):
    rig = Rig(tmp_path)
    rig.warm()
    (tmp_path / "weather.db").write_bytes(b"corrupted")
    rig.service.run_cycle()
    before = len(rig.driver.commands)
    assert rig.service.drain().state is State.FAULT
    assert rig.driver.commands[before:] == [Command.DRAIN]


def test_weather_status_finishes_expired_manual_without_starting_auto(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    rig.service.start_timed_shower(180)
    rig.result()
    rig.service.run_cycle()
    rig.advance(180)
    assert rig.service.weather_status().operation == "MANUAL_IDLE"
    assert rig.driver.commands[-1] is Command.DRAIN


def test_restarted_manual_marker_requires_fresh_start(tmp_path):
    rig = Rig(tmp_path)
    rig.service.startup()
    rig.service.start_timed_shower(180)
    rig.coordinator = WeatherCoordinator(
        rig.store, rig.worker, lambda: rig.now, lambda: rig.mono
    )
    restarted = rig.new_service()
    restarted.startup()
    rig.result()
    assert restarted.run_cycle().command is Command.DRAIN
    assert restarted.weather_status().operation == "USER_OFF"
    assert restarted.status().remaining_seconds == 0
