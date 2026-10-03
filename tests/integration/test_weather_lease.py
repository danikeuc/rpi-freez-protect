"""Real daemon parser/lease over fake whole-pair GPIO registers; no device access."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from test_paired_gpio_daemon import FakeRegisters, load_daemon

from freeze_protect.adapters.simulation import (
    InMemoryEventStore,
    SimulatedForecastClient,
    SimulatedForecastStore,
    SimulatedTemperatureSource,
)
from freeze_protect.application.ports import AdapterError
from freeze_protect.application.service import ControlService
from freeze_protect.application.weather_control import WeatherCoordinator
from freeze_protect.application.weather_worker import WeatherResult
from freeze_protect.domain.models import (
    ActuatorCommand,
    ActuatorReceipt,
    ControllerState,
    ControlMode,
    SafetySettings,
    SensorHealth,
    SupplyAction,
    TemperatureReading,
)
from freeze_protect.domain.weather import WeatherSettings, WeatherWindow
from freeze_protect.persistence.weather import SQLiteWeatherStore


def build_service(tmp_path, driver, elapsed):
    now = datetime(2026, 10, 3, 10, tzinfo=UTC)
    store = SQLiteWeatherStore(tmp_path / "weather.db")
    record = store.load()
    store.compare_and_swap(
        record.control_revision,
        replace(record, settings=WeatherSettings(True, 46.5, 15.5)),
    )

    class Worker:
        result = None

        def submit(self, request):
            today = request.requested_at.astimezone(
                ZoneInfo(request.settings.timezone)
            ).date()
            window = WeatherWindow(
                tuple(today + timedelta(days=i) for i in range(5)),
                (5.0,) * 5,
                request.requested_at,
                46.5,
                15.5,
                request.settings.timezone,
                request.settings.revision,
                request.generation,
            )
            self.result = WeatherResult(request, window, None, elapsed[0])
            return True

        def poll(self):
            result, self.result = self.result, None
            return result

        def cancel(self):
            self.result = None

    clock = lambda: now + timedelta(seconds=elapsed[0])
    coordinator = WeatherCoordinator(store, Worker(), clock, lambda: elapsed[0])
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            TemperatureReading(None, now, SensorHealth.INVALID)
        ),
        forecast_store=SimulatedForecastStore(),
        forecast_client=SimulatedForecastClient(),
        actuator_driver=driver,
        event_store=InMemoryEventStore(),
        settings=SafetySettings(),
        clock=clock,
        monotonic_clock=lambda: elapsed[0],
        mode=ControlMode.WEATHER_ASSISTED,
        weather_coordinator=coordinator,
        weather_store=store,
    )
    return service, store


@pytest.mark.parametrize("failure", ["expired_renew", "lost_begin", "wrong_action"])
def test_weather_lease_failure_never_reopens_pair(tmp_path, failure):
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    elapsed = [0.0]
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: elapsed[0])
    actions = []

    class Driver:
        def command(self, command, *, supply_action=None):
            request = {
                "command": command.value,
                "protocol_version": 2,
                "deadline_unix_ms": 1000.0,
            }
            if supply_action is not None:
                actions.append(supply_action)
                request["supply_action"] = supply_action.value
            result = daemon.execute_request(request, lease, clock=lambda: 0.0)
            if not result["ok"]:
                raise AdapterError(result["error"])
            if failure == "lost_begin" and supply_action is SupplyAction.BEGIN:
                raise AdapterError("receipt lost")
            return ActuatorReceipt(
                command,
                "trace",
                result["gpio"]["26"],
                result["gpio"]["20"],
                "trace",
                2,
                SupplyAction.RENEW
                if failure == "wrong_action" and supply_action is SupplyAction.BEGIN
                else supply_action,
            )

    service, store = build_service(tmp_path, Driver(), elapsed)
    service.startup()
    result = service.run_cycle()
    if failure == "expired_renew":
        assert result.state is ControllerState.AUTO_SUPPLY
        elapsed[0] = 60
        assert lease.enforce()
        assert service.run_cycle().state is ControllerState.FAULT
        assert actions == [SupplyAction.BEGIN, SupplyAction.RENEW]
    else:
        assert result.state is ControllerState.FAULT
        assert actions == [SupplyAction.BEGIN]
    assert store.load().fault_inhibited
    for _ in range(3):
        assert service.run_cycle().state is ControllerState.FAULT
    assert registers.writes.count((daemon.GPCLR0, daemon.PAIR_MASK)) == 1
    assert all(mask == daemon.PAIR_MASK for _, mask in registers.writes)
    assert registers.level & daemon.PAIR_MASK == daemon.PAIR_MASK
    assert service.status().command is ActuatorCommand.DRAIN
