from threading import Event

from freeze_protect.application.service import PeriodicControlLoop


class CountingService:
    def __init__(self) -> None:
        self.first_cycle = Event()
        self.second_cycle = Event()
        self.cycles = 0

    def refresh_forecast(self) -> None:
        return None

    def run_cycle(self) -> None:
        self.cycles += 1
        if self.cycles == 1:
            self.first_cycle.set()
        if self.cycles == 2:
            self.second_cycle.set()

    def seconds_until_timed_shower_expiry(self) -> float | None:
        return None

    def handle_persistence_failure(self) -> None:
        raise AssertionError("the loop should not fault in this test")


def test_wake_interrupts_a_normal_cycle_wait_for_a_new_timed_shower() -> None:
    service = CountingService()
    loop = PeriodicControlLoop(
        service,  # type: ignore[arg-type]
        cycle_interval_s=10.0,
        forecast_interval_s=100.0,
    )
    loop.start()
    try:
        assert service.first_cycle.wait(timeout=1.0)
        loop.wake()
        assert service.second_cycle.wait(timeout=1.0)
    finally:
        loop.stop()


def test_stalled_weather_worker_cannot_block_manual_renewal_or_expiry(tmp_path):
    from test_weather_service import Rig

    from freeze_protect.application.weather_control import WeatherCoordinator
    from freeze_protect.application.weather_worker import WeatherWorker
    from freeze_protect.domain.models import (
        ActuatorCommand,
        ControllerState,
        SupplyAction,
    )

    rig = Rig(tmp_path)
    entered, release = Event(), Event()

    def fetch(*args):
        entered.set()
        release.wait(2)
        raise RuntimeError("injected stalled transport")

    worker = WeatherWorker(fetch, lambda: None, lambda: rig.mono)
    rig.coordinator = WeatherCoordinator(
        rig.store, worker, lambda: rig.now, lambda: rig.mono
    )
    rig.service = rig.new_service()
    try:
        rig.service.startup()
        assert entered.wait(1)
        assert (
            rig.service.start_weather_shower(180).state is ControllerState.TIMED_SHOWER
        )
        for _ in range(5):
            rig.advance(30)
            assert rig.service.run_cycle().state is ControllerState.TIMED_SHOWER
            assert rig.driver.actions[-1] is SupplyAction.RENEW
        rig.advance(30)
        assert rig.service.run_cycle().command is ActuatorCommand.DRAIN
        assert not release.is_set()
        rig.service.shutdown()
        assert rig.store.load().active_marker is None
    finally:
        release.set()
        worker.stop()


def test_weather_result_wakes_loop_and_legacy_fetch_is_never_called(tmp_path):
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    from test_weather_service import Rig

    from freeze_protect.application.weather_control import WeatherCoordinator
    from freeze_protect.application.weather_worker import WeatherWorker
    from freeze_protect.domain.models import ActuatorCommand
    from freeze_protect.domain.weather import WeatherWindow

    rig = Rig(tmp_path)
    release, entered, supplied = Event(), Event(), Event()

    def fetch(settings, requested_at, generation):
        entered.set()
        release.wait(2)
        today = requested_at.astimezone(ZoneInfo(settings.timezone)).date()
        return WeatherWindow(
            tuple(today + timedelta(days=i) for i in range(5)),
            (5.0,) * 5,
            requested_at,
            settings.latitude,
            settings.longitude,
            settings.timezone,
            settings.revision,
            generation,
        )

    # The callback captures the loop, which is created before startup submits.
    worker = WeatherWorker(fetch, lambda: loop.wake(), lambda: rig.mono)
    rig.coordinator = WeatherCoordinator(
        rig.store, worker, lambda: rig.now, lambda: rig.mono
    )
    rig.service = rig.new_service()
    loop = PeriodicControlLoop(rig.service, cycle_interval_s=1000)
    original = rig.driver.command

    def command(command, **kwargs):
        result = original(command, **kwargs)
        if command is ActuatorCommand.SUPPLY:
            supplied.set()
        return result

    rig.driver.command = command

    def forbidden(*args):
        raise AssertionError("legacy fetch must not run in weather mode")

    rig.service._forecast_client.fetch = forbidden
    try:
        assert loop._cycle_interval_s == 30
        rig.service.startup()
        assert entered.wait(1)
        loop.start()
        release.set()
        assert supplied.wait(1)
    finally:
        release.set()
        loop.stop()
        rig.service.shutdown()
        worker.stop()
