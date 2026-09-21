from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Event, RLock, Thread
from time import monotonic
from uuid import uuid4

from freeze_protect.application.ports import (
    ActuatorDriver,
    AdapterError,
    EventStore,
    ForecastClient,
    ForecastStore,
    TemperatureSource,
)
from freeze_protect.domain.models import (
    ActuatorCommand,
    ActuatorReceipt,
    AuditEvent,
    ControllerState,
    Decision,
    ForecastSnapshot,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)
from freeze_protect.domain.policy import evaluate_automatic


@dataclass(frozen=True, slots=True)
class ControlStatus:
    state: ControllerState
    reason: str
    last_reading: TemperatureReading | None
    forecast: ForecastSnapshot | None
    timed_shower_deadline: datetime | None
    last_receipt: ActuatorReceipt | None


class ControlService:
    """Coordinates safety policy, persistent weather, and one paired actuator."""

    def __init__(
        self,
        *,
        temperature_source: TemperatureSource,
        forecast_store: ForecastStore,
        forecast_client: ForecastClient,
        actuator_driver: ActuatorDriver,
        event_store: EventStore,
        settings: SafetySettings,
        clock: Callable[[], datetime],
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._temperature_source = temperature_source
        self._forecast_store = forecast_store
        self._forecast_client = forecast_client
        self._actuator_driver = actuator_driver
        self._event_store = event_store
        self._settings = settings
        self._clock = clock
        self._monotonic_clock = monotonic_clock
        self._lock = RLock()
        self._state = ControllerState.STARTING
        self._last_decision = Decision(
            ControllerState.STARTING, ActuatorCommand.DRAIN, "starting"
        )
        self._last_reading: TemperatureReading | None = None
        self._last_receipt: ActuatorReceipt | None = None
        self._last_command: ActuatorCommand | None = None
        self._timed_shower_deadline: datetime | None = None
        self._timed_shower_monotonic_deadline: float | None = None
        self._persistence_fault_latched = False

    @property
    def settings(self) -> SafetySettings:
        return self._settings

    def update_settings(self, settings: SafetySettings) -> Decision:
        with self._lock:
            self._settings = settings
            if not self._append_event(
                "settings_changed",
                {"settings_version": settings.settings_version},
            ):
                return self._last_decision
            return self._run_automatic()

    def startup(self) -> Decision:
        """Force physical drain after every process start before evaluating inputs."""
        with self._lock:
            self._timed_shower_deadline = None
            self._timed_shower_monotonic_deadline = None
            if not self._send(ActuatorCommand.DRAIN, force=True):
                return self._fault("startup_drain_failed")
            if not self._append_event("startup_drain", {"command": "DRAIN"}):
                return self._last_decision
            return self._run_automatic()

    def run_cycle(self) -> Decision:
        with self._lock:
            if self._state is ControllerState.FAULT:
                return self._last_decision
            if self._timed_shower_deadline is not None:
                if (
                    self._timed_shower_monotonic_deadline is not None
                    and self._monotonic_clock() < self._timed_shower_monotonic_deadline
                ):
                    if not self._send(ActuatorCommand.SUPPLY, force=True):
                        self._best_effort_drain()
                        return self._fault("relay_driver_error")
                    return self._set_decision(
                        Decision(
                            ControllerState.TIMED_SHOWER,
                            ActuatorCommand.SUPPLY,
                            "timed_shower_active",
                        )
                    )
                return self._finish_timed_shower()
            return self._run_automatic()

    def start_timed_shower(self) -> Decision:
        with self._lock:
            if self._state is ControllerState.FAULT:
                return self._last_decision
            if self._timed_shower_deadline is not None:
                return self._set_decision(
                    Decision(
                        ControllerState.TIMED_SHOWER,
                        ActuatorCommand.SUPPLY,
                        "timed_shower_active",
                    )
                )
            duration_s = min(
                self._settings.timed_shower_default_s,
                self._settings.timed_shower_max_s,
            )
            deadline = self._clock() + timedelta(seconds=duration_s)
            if not self._send(ActuatorCommand.SUPPLY):
                self._best_effort_drain()
                return self._fault("relay_driver_error")
            self._timed_shower_deadline = deadline
            self._timed_shower_monotonic_deadline = self._monotonic_clock() + duration_s
            decision = self._set_decision(
                Decision(
                    ControllerState.TIMED_SHOWER,
                    ActuatorCommand.SUPPLY,
                    "timed_shower_started",
                )
            )
            if not self._append_event(
                "timed_shower_started",
                {"deadline": deadline.isoformat(), "command": "SUPPLY"},
            ):
                return self._last_decision
            return decision

    def drain(self, reason: str = "drain_requested") -> Decision:
        with self._lock:
            self._timed_shower_deadline = None
            self._timed_shower_monotonic_deadline = None
            if not self._send(ActuatorCommand.DRAIN, force=True):
                return self._fault("relay_driver_error")
            decision = self._set_decision(
                Decision(
                    ControllerState.FROST_PROTECTION,
                    ActuatorCommand.DRAIN,
                    reason,
                )
            )
            if not self._append_event("drain_requested", {"reason": reason}):
                return self._last_decision
            return decision

    def clear_fault(self) -> Decision:
        with self._lock:
            if (
                self._state is not ControllerState.FAULT
                or self._persistence_fault_latched
            ):
                return self._last_decision
            if not self._send(ActuatorCommand.DRAIN, force=True):
                return self._last_decision
            self._state = ControllerState.FROST_PROTECTION
            if not self._append_event("fault_cleared", {"command": "DRAIN"}):
                return self._last_decision
            return self._run_automatic()

    def refresh_forecast(self) -> ForecastSnapshot | None:
        with self._lock:
            if self._settings.latitude is None or self._settings.longitude is None:
                self._append_event(
                    "forecast_refresh_skipped", {"reason": "location_missing"}
                )
                return None
            try:
                snapshot = self._forecast_client.fetch(self._settings, self._clock())
                self._forecast_store.save(snapshot)
            except AdapterError as error:
                self._append_event("forecast_refresh_failed", {"error": str(error)})
                return None
            except Exception:  # noqa: BLE001 - persistence ports are user supplied.
                self._latch_persistence_failure()
                return None
            if not self._append_event(
                "forecast_refreshed",
                {"fetched_at": snapshot.fetched_at.isoformat()},
            ):
                return None
            return snapshot

    def status(self) -> ControlStatus:
        with self._lock:
            forecast = self._load_forecast()
            return ControlStatus(
                state=self._state,
                reason=self._last_decision.reason,
                last_reading=self._last_reading,
                forecast=forecast,
                timed_shower_deadline=self._timed_shower_deadline,
                last_receipt=self._last_receipt,
            )

    def seconds_until_timed_shower_expiry(self) -> float | None:
        with self._lock:
            if self._timed_shower_monotonic_deadline is None:
                return None
            return max(
                0.0,
                self._timed_shower_monotonic_deadline - self._monotonic_clock(),
            )

    def _finish_timed_shower(self) -> Decision:
        self._timed_shower_deadline = None
        self._timed_shower_monotonic_deadline = None
        if not self._send(ActuatorCommand.DRAIN, force=True):
            return self._fault("relay_driver_error")
        decision = self._set_decision(
            Decision(
                ControllerState.FROST_PROTECTION,
                ActuatorCommand.DRAIN,
                "timed_shower_expired",
            )
        )
        if not self._append_event("timed_shower_expired", {"command": "DRAIN"}):
            return self._last_decision
        return decision

    def _run_automatic(self) -> Decision:
        if self._is_faulted():
            return self._last_decision
        reading = self._read_temperature()
        if self._is_faulted():
            return self._last_decision
        forecast = self._load_forecast()
        if self._is_faulted():
            return self._last_decision
        decision = evaluate_automatic(
            reading=reading,
            forecast=forecast,
            settings=self._settings,
            now=self._clock(),
        )
        if not self._send(
            decision.command,
            force=decision.command is ActuatorCommand.SUPPLY,
        ):
            if decision.command is ActuatorCommand.SUPPLY:
                self._best_effort_drain()
            return self._fault("relay_driver_error")
        self._set_decision(decision)
        if not self._append_event(
            "automatic_decision",
            {
                "state": decision.state.value,
                "command": decision.command.value,
                "reason": decision.reason,
            },
        ):
            return self._last_decision
        return decision

    def _is_faulted(self) -> bool:
        return self._state is ControllerState.FAULT

    def _read_temperature(self) -> TemperatureReading:
        now = self._clock()
        try:
            reading = self._temperature_source.read()
        except AdapterError as error:
            self._append_event("sensor_source_error", {"error": str(error)})
            reading = TemperatureReading(None, now, SensorHealth.STALE)
        except Exception:  # noqa: BLE001 - persistence ports are user supplied.
            self._latch_persistence_failure()
            reading = TemperatureReading(None, now, SensorHealth.STALE)
        self._last_reading = reading
        return reading

    def _load_forecast(self) -> ForecastSnapshot | None:
        try:
            return self._forecast_store.load()
        except Exception:  # noqa: BLE001 - persistence ports are user supplied.
            self._latch_persistence_failure()
            return None

    def _send(
        self,
        command: ActuatorCommand,
        *,
        force: bool = False,
        record_error: bool = True,
    ) -> bool:
        if not force and command is self._last_command:
            return True
        attempts = 2 if command is ActuatorCommand.DRAIN else 1
        for attempt in range(1, attempts + 1):
            try:
                self._last_receipt = self._actuator_driver.command(command)
            except AdapterError as error:
                if record_error and not self._append_event(
                    "relay_driver_error",
                    {
                        "command": command.value,
                        "attempt": attempt,
                        "error": str(error),
                    },
                ):
                    return False
                continue
            self._last_command = command
            return True
        return False

    def _best_effort_drain(self) -> None:
        self._send(ActuatorCommand.DRAIN, force=True)

    def _fault(self, reason: str) -> Decision:
        if self._persistence_fault_latched:
            return self._last_decision
        self._timed_shower_deadline = None
        self._timed_shower_monotonic_deadline = None
        decision = Decision(ControllerState.FAULT, ActuatorCommand.DRAIN, reason)
        self._set_decision(decision)
        self._append_event("fault", {"reason": reason})
        return self._last_decision

    def _set_decision(self, decision: Decision) -> Decision:
        if (
            self._persistence_fault_latched
            and decision.state is not ControllerState.FAULT
        ):
            return self._last_decision
        self._state = decision.state
        self._last_decision = decision
        return decision

    def handle_persistence_failure(self) -> Decision:
        with self._lock:
            self._latch_persistence_failure()
            return self._last_decision

    def _append_event(self, event_type: str, payload: dict[str, object]) -> bool:
        try:
            self._event_store.append(
                AuditEvent(
                    id=str(uuid4()),
                    occurred_at=self._clock(),
                    event_type=event_type,
                    payload=payload,
                )
            )
        except Exception:  # noqa: BLE001 - persistence ports are user supplied.
            self._latch_persistence_failure()
            return False
        return True

    def _latch_persistence_failure(self) -> None:
        if self._persistence_fault_latched:
            return
        self._persistence_fault_latched = True
        self._timed_shower_deadline = None
        self._timed_shower_monotonic_deadline = None
        self._send(ActuatorCommand.DRAIN, force=True, record_error=False)
        self._state = ControllerState.FAULT
        self._last_decision = Decision(
            ControllerState.FAULT,
            ActuatorCommand.DRAIN,
            "persistence_error",
        )


class PeriodicControlLoop:
    def __init__(
        self,
        service: ControlService,
        *,
        cycle_interval_s: float = 30.0,
        forecast_interval_s: float = 3_600.0,
    ) -> None:
        self._service = service
        self._cycle_interval_s = cycle_interval_s
        self._forecast_interval_s = forecast_interval_s
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="freeze-protect-cycle", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=self._cycle_interval_s + 1)
            self._thread = None

    def wake(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        next_forecast = 0.0
        while not self._stop.is_set():
            self._wake.clear()
            try:
                if monotonic() >= next_forecast:
                    self._service.refresh_forecast()
                    next_forecast = monotonic() + self._forecast_interval_s
                self._service.run_cycle()
            except Exception:  # noqa: BLE001 - fail-safe loop boundary.
                self._service.handle_persistence_failure()
            wait_seconds = self._cycle_interval_s
            shower_expiry = self._service.seconds_until_timed_shower_expiry()
            if shower_expiry is not None:
                wait_seconds = min(wait_seconds, shower_expiry)
            self._wake.wait(wait_seconds)
