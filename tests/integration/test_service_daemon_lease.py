"""Hub cycle through the real daemon request parser and lease authority."""

from datetime import UTC, datetime

from test_paired_gpio_daemon import FakeRegisters, load_daemon

from freeze_protect.adapters.simulation import (
    InMemoryEventStore,
    SimulatedForecastClient,
    SimulatedForecastStore,
    SimulatedTemperatureSource,
)
from freeze_protect.application.ports import AdapterError
from freeze_protect.application.service import ControlService
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


def test_late_hub_renewal_faults_and_clears_timer_without_second_low_write() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    elapsed = [0.0]
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: elapsed[0])

    class DaemonDriver:
        def command(
            self, command: ActuatorCommand, *, supply_action: SupplyAction | None = None
        ) -> ActuatorReceipt:
            request = {
                "command": command.value,
                "protocol_version": 2,
                "deadline_unix_ms": 1000.0,
            }
            if supply_action is not None:
                request["supply_action"] = supply_action.value
            result = daemon.execute_request(request, lease, clock=lambda: 0.0)
            if not result["ok"]:
                raise AdapterError(result["error"])
            return ActuatorReceipt(
                command,
                "trace",
                result["gpio"]["26"],
                result["gpio"]["20"],
                "trace",
                2,
                supply_action,
            )

    now = datetime(2026, 10, 2, tzinfo=UTC)
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            TemperatureReading(None, now, SensorHealth.CALIBRATION_REQUIRED)
        ),
        forecast_store=SimulatedForecastStore(),
        forecast_client=SimulatedForecastClient(),
        actuator_driver=DaemonDriver(),
        event_store=InMemoryEventStore(),
        settings=SafetySettings(),
        clock=lambda: now,
        monotonic_clock=lambda: elapsed[0],
        mode=ControlMode.MANUAL_TIMED,
    )
    assert service.startup().state is ControllerState.MANUAL_DRAIN
    assert service.start_timed_shower().state is ControllerState.TIMED_SHOWER
    assert registers.writes.count((daemon.GPCLR0, daemon.PAIR_MASK)) == 1
    elapsed[0] = 60.0
    assert lease.enforce() is True
    assert lease.execute("DRAIN")["ok"] is True  # independent bridge restart
    assert service.run_cycle().state is ControllerState.FAULT
    assert service.seconds_until_timed_shower_expiry() is None
    assert registers.writes.count((daemon.GPCLR0, daemon.PAIR_MASK)) == 1
    assert registers.level & daemon.PAIR_MASK == daemon.PAIR_MASK


def test_lost_begin_receipt_drains_and_never_retries_begin() -> None:
    daemon = load_daemon()
    registers = FakeRegisters(daemon)
    lease = daemon.SupplyLease(daemon.PairedGpio(registers), clock=lambda: 0.0)
    actions: list[str] = []

    class LostReceiptDriver:
        def command(
            self, command: ActuatorCommand, *, supply_action: SupplyAction | None = None
        ) -> ActuatorReceipt:
            request = {
                "command": command.value,
                "protocol_version": 2,
                "deadline_unix_ms": 1000.0,
            }
            if supply_action is not None:
                actions.append(supply_action.value)
                request["supply_action"] = supply_action.value
            result = daemon.execute_request(request, lease, clock=lambda: 0.0)
            if not result["ok"]:
                raise AdapterError(result["error"])
            if supply_action is SupplyAction.BEGIN:
                raise AdapterError("receipt lost after accepted begin")
            return ActuatorReceipt(
                command,
                "trace",
                result["gpio"]["26"],
                result["gpio"]["20"],
                "trace",
                2,
                supply_action,
            )

    now = datetime(2026, 10, 2, tzinfo=UTC)
    service = ControlService(
        temperature_source=SimulatedTemperatureSource(
            TemperatureReading(None, now, SensorHealth.CALIBRATION_REQUIRED)
        ),
        forecast_store=SimulatedForecastStore(),
        forecast_client=SimulatedForecastClient(),
        actuator_driver=LostReceiptDriver(),
        event_store=InMemoryEventStore(),
        settings=SafetySettings(),
        clock=lambda: now,
        monotonic_clock=lambda: 0.0,
        mode=ControlMode.MANUAL_TIMED,
    )
    service.startup()
    assert service.start_timed_shower().state is ControllerState.FAULT
    assert service.seconds_until_timed_shower_expiry() is None
    assert actions == ["begin"]
    assert registers.writes.count((daemon.GPCLR0, daemon.PAIR_MASK)) == 1
    assert registers.level & daemon.PAIR_MASK == daemon.PAIR_MASK
