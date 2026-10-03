from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from math import ceil
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
from freeze_protect.application.weather_control import WeatherCoordinator
from freeze_protect.domain.models import (
    ActuatorCommand,
    ActuatorReceipt,
    AuditEvent,
    ControllerState,
    ControlMode,
    Decision,
    ForecastSnapshot,
    SafetySettings,
    SensorHealth,
    SupplyAction,
    TemperatureReading,
)
from freeze_protect.domain.policy import evaluate_automatic
from freeze_protect.domain.weather import (
    WEATHER_PROCESSING_BOUND_SECONDS,
    WeatherControlRecord,
    WeatherEligibility,
    WeatherObservation,
    WeatherSettings,
)
from freeze_protect.persistence.weather import (
    SQLiteWeatherStore,
    WeatherRevisionConflict,
    WeatherStateError,
)


@dataclass(frozen=True, slots=True)
class WeatherControlStatus:
    record: WeatherControlRecord
    operation: str
    eligibility: WeatherEligibility
    observation: WeatherObservation | None


@dataclass(frozen=True, slots=True)
class ControlStatus:
    mode: ControlMode
    command: ActuatorCommand
    remaining_seconds: int
    state: ControllerState
    reason: str
    last_reading: TemperatureReading | None
    forecast: ForecastSnapshot | None
    timed_shower_deadline: datetime | None
    last_receipt: ActuatorReceipt | None


class ControlService:
    """Coordinates safety policy, persistent weather, and one paired actuator."""

    MANUAL_TIMED_DURATION_S = 600

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
        mode: ControlMode = ControlMode.SAFE_DRAIN,
        weather_coordinator: WeatherCoordinator | None = None,
        weather_store: SQLiteWeatherStore | None = None,
    ) -> None:
        self._temperature_source = temperature_source
        self._forecast_store = forecast_store
        self._forecast_client = forecast_client
        self._actuator_driver = actuator_driver
        self._event_store = event_store
        self._settings = settings
        self._mode = mode
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
        self._timed_shower_duration_s: int | None = None
        self._persistence_fault_latched = False
        self._supply_ready = False
        self._weather_coordinator = weather_coordinator
        self._weather_store = weather_store
        self._weather_started = False

    @property
    def settings(self) -> SafetySettings:
        return self._settings

    @property
    def mode(self) -> ControlMode:
        return self._mode

    def update_settings(self, settings: SafetySettings) -> Decision:
        with self._lock:
            self._settings = settings
            if not self._append_event(
                "settings_changed",
                {"settings_version": settings.settings_version},
            ):
                return self._last_decision
            if self._timed_shower_deadline is not None and self._mode in (
                ControlMode.MANUAL_TIMED,
                ControlMode.WEATHER_ASSISTED,
            ):
                if (
                    self._timed_shower_duration_s is not None
                    and settings.timed_shower_max_s < self._timed_shower_duration_s
                ):
                    return self.drain("manual_duration_exceeds_settings_limit")
                return self._last_decision
            return self._run_idle()

    def startup(self) -> Decision:
        """Force physical drain after every process start before evaluating inputs."""
        with self._lock:
            self._supply_ready = False
            self._last_command = None
            self._timed_shower_deadline = None
            self._timed_shower_monotonic_deadline = None
            self._timed_shower_duration_s = None
            if not self._send(ActuatorCommand.DRAIN, force=True):
                return self._fault("startup_drain_failed")
            if not self._append_event("startup_drain", {"command": "DRAIN"}):
                return self._last_decision
            if self._mode is ControlMode.WEATHER_ASSISTED:
                return self._startup_weather()
            if self._mode is not ControlMode.AUTOMATIC:
                return self._set_decision(
                    Decision(
                        self._idle_state(),
                        ActuatorCommand.DRAIN,
                        "manual_idle"
                        if self._mode is ControlMode.MANUAL_TIMED
                        else "safe_drain",
                    )
                )
            return self._run_idle()

    def run_cycle(self) -> Decision:
        with self._lock:
            if self._state is ControllerState.FAULT:
                return self._last_decision
            if self._mode is ControlMode.WEATHER_ASSISTED:
                return self._run_weather()
            if self._timed_shower_deadline is not None:
                if (
                    self._timed_shower_monotonic_deadline is not None
                    and self._monotonic_clock() < self._timed_shower_monotonic_deadline
                ):
                    if not self._send(
                        ActuatorCommand.SUPPLY,
                        force=True,
                        supply_action=SupplyAction.RENEW,
                    ):
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
            return self._run_idle()

    def start_timed_shower(self, duration_seconds: int | None = None) -> Decision:
        if duration_seconds is not None and (
            type(duration_seconds) is not int
            or not 60 <= duration_seconds <= 600
            or duration_seconds % 60 != 0
        ):
            raise ValueError("duration_seconds must be a whole minute from 60 to 600")
        with self._lock:
            if self._mode is ControlMode.WEATHER_ASSISTED:
                return self._start_weather_manual(
                    self.MANUAL_TIMED_DURATION_S
                    if duration_seconds is None
                    else duration_seconds
                )
            if self._state is ControllerState.FAULT:
                return self._last_decision
            if (
                duration_seconds is not None
                and self._mode is not ControlMode.MANUAL_TIMED
            ):
                return Decision(
                    self._state,
                    self._last_decision.command,
                    "manual_duration_requires_manual_mode",
                )
            if self._mode is ControlMode.SAFE_DRAIN:
                idle_decision = self._run_idle()
                if idle_decision.state is ControllerState.FAULT:
                    return idle_decision
                return self._set_decision(
                    Decision(
                        ControllerState.SAFE_DRAIN,
                        ActuatorCommand.DRAIN,
                        "operating_mode_not_configured",
                    )
                )
            if self._timed_shower_deadline is not None:
                if (
                    self._timed_shower_monotonic_deadline is None
                    or self._monotonic_clock() >= self._timed_shower_monotonic_deadline
                ):
                    return self._finish_timed_shower()
                return self._set_decision(
                    Decision(
                        ControllerState.TIMED_SHOWER,
                        ActuatorCommand.SUPPLY,
                        "timed_shower_active",
                    )
                )
            if self._mode is ControlMode.MANUAL_TIMED:
                duration_s = (
                    self.MANUAL_TIMED_DURATION_S
                    if duration_seconds is None
                    else duration_seconds
                )
                if self._settings.timed_shower_max_s < duration_s:
                    return self._set_decision(
                        Decision(
                            ControllerState.MANUAL_DRAIN,
                            ActuatorCommand.DRAIN,
                            "manual_duration_exceeds_settings_limit",
                        )
                    )
            else:
                duration_s = min(
                    self._settings.timed_shower_default_s,
                    self._settings.timed_shower_max_s,
                )
            deadline = self._clock() + timedelta(seconds=duration_s)
            action = (
                SupplyAction.RENEW
                if self._last_command is ActuatorCommand.SUPPLY
                else SupplyAction.BEGIN
            )
            if not self._send(ActuatorCommand.SUPPLY, force=True, supply_action=action):
                self._best_effort_drain()
                return self._fault("relay_driver_error")
            self._timed_shower_deadline = deadline
            self._timed_shower_monotonic_deadline = self._monotonic_clock() + duration_s
            self._timed_shower_duration_s = duration_s
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
            if self._mode is ControlMode.WEATHER_ASSISTED:
                if reason == "shutdown_drain":
                    return self.shutdown()
                return self._drain_weather(reason, inhibit=True)
            self._timed_shower_deadline = None
            self._timed_shower_monotonic_deadline = None
            self._timed_shower_duration_s = None
            if not self._send(ActuatorCommand.DRAIN, force=True):
                return self._fault("relay_driver_error")
            decision = self._set_decision(
                Decision(
                    self._idle_state(),
                    ActuatorCommand.DRAIN,
                    reason,
                )
            )
            if not self._append_event("drain_requested", {"reason": reason}):
                return self._last_decision
            return decision

    def clear_fault(self) -> Decision:
        with self._lock:
            if self._mode is ControlMode.WEATHER_ASSISTED:
                return self._clear_weather_fault()
            if (
                self._state is not ControllerState.FAULT
                or self._persistence_fault_latched
            ):
                return self._last_decision
            if not self._send(ActuatorCommand.DRAIN, force=True):
                return self._last_decision
            self._state = self._idle_state()
            if not self._append_event("fault_cleared", {"command": "DRAIN"}):
                return self._last_decision
            return self._run_idle()

    def refresh_forecast(self) -> ForecastSnapshot | None:
        with self._lock:
            if self._mode is not ControlMode.AUTOMATIC:
                return None
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
            remaining_seconds = 0
            if self._timed_shower_monotonic_deadline is not None:
                remaining = (
                    self._timed_shower_monotonic_deadline - self._monotonic_clock()
                )
                if remaining <= 0:
                    self._finish_timed_shower()
                else:
                    remaining_seconds = ceil(remaining)
                    if self._mode is ControlMode.MANUAL_TIMED:
                        remaining_seconds = min(
                            remaining_seconds, self.MANUAL_TIMED_DURATION_S
                        )
            forecast = (
                self._load_forecast() if self._mode is ControlMode.AUTOMATIC else None
            )
            return ControlStatus(
                mode=self._mode,
                command=self._last_decision.command,
                remaining_seconds=remaining_seconds,
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
        if self._mode is ControlMode.WEATHER_ASSISTED:
            return self._drain_weather("timed_shower_expired", inhibit=False)
        self._timed_shower_deadline = None
        self._timed_shower_monotonic_deadline = None
        self._timed_shower_duration_s = None
        if not self._send(ActuatorCommand.DRAIN, force=True):
            return self._fault("relay_driver_error")
        decision = self._set_decision(
            Decision(
                self._idle_state(),
                ActuatorCommand.DRAIN,
                "timed_shower_expired",
            )
        )
        if not self._append_event("timed_shower_expired", {"command": "DRAIN"}):
            return self._last_decision
        return decision

    def _idle_state(self) -> ControllerState:
        if self._mode in (ControlMode.MANUAL_TIMED, ControlMode.WEATHER_ASSISTED):
            return ControllerState.MANUAL_DRAIN
        if self._mode is ControlMode.SAFE_DRAIN:
            return ControllerState.SAFE_DRAIN
        return ControllerState.FROST_PROTECTION

    def _run_idle(self) -> Decision:
        if self._mode is ControlMode.WEATHER_ASSISTED:
            return self._run_weather()
        if self._mode is ControlMode.AUTOMATIC:
            return self._run_automatic()
        if self._is_faulted():
            return self._last_decision
        if not self._send(ActuatorCommand.DRAIN, force=True):
            return self._fault("relay_driver_error")
        return self._set_decision(
            Decision(
                self._idle_state(),
                ActuatorCommand.DRAIN,
                "manual_idle"
                if self._mode is ControlMode.MANUAL_TIMED
                else "safe_drain",
            )
        )

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
            supply_action=(
                SupplyAction.RENEW
                if self._last_command is ActuatorCommand.SUPPLY
                else SupplyAction.BEGIN
            )
            if decision.command is ActuatorCommand.SUPPLY
            else None,
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
        supply_action: SupplyAction | None = None,
    ) -> bool:
        if command is ActuatorCommand.SUPPLY and (
            not self._supply_ready or supply_action is None
        ):
            return False
        if not force and command is self._last_command:
            return True
        attempts = 2 if command is ActuatorCommand.DRAIN else 1
        for attempt in range(1, attempts + 1):
            try:
                receipt = self._actuator_driver.command(
                    command, supply_action=supply_action
                )
                if (
                    receipt.command is not command
                    or receipt.protocol_version != 2
                    or receipt.supply_action is not supply_action
                    or (receipt.gpio_26, receipt.gpio_20)
                    != ((0, 0) if command is ActuatorCommand.SUPPLY else (1, 1))
                ):
                    raise AdapterError("actuator receipt protocol mismatch")
            except Exception as error:
                if (
                    not isinstance(error, AdapterError)
                    and self._mode is not ControlMode.WEATHER_ASSISTED
                ):
                    raise
                if record_error and not self._append_event(
                    "relay_driver_error",
                    {
                        "command": command.value,
                        "attempt": attempt,
                        "error": str(error)
                        if isinstance(error, AdapterError)
                        else "actuator_failure",
                    },
                ):
                    return False
                continue
            self._last_receipt = receipt
            self._last_command = command
            if command is ActuatorCommand.DRAIN:
                self._supply_ready = True
            return True
        return False

    def _best_effort_drain(self) -> None:
        self._send(ActuatorCommand.DRAIN, force=True)

    def _fault(self, reason: str) -> Decision:
        if self._persistence_fault_latched:
            return self._last_decision
        self._timed_shower_deadline = None
        self._timed_shower_monotonic_deadline = None
        self._timed_shower_duration_s = None
        decision = Decision(ControllerState.FAULT, ActuatorCommand.DRAIN, reason)
        self._set_decision(decision)
        self._persist_weather_fault()
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
        self._persist_weather_fault()
        self._timed_shower_deadline = None
        self._timed_shower_monotonic_deadline = None
        self._timed_shower_duration_s = None
        self._send(ActuatorCommand.DRAIN, force=True, record_error=False)
        self._state = ControllerState.FAULT
        self._last_decision = Decision(
            ControllerState.FAULT,
            ActuatorCommand.DRAIN,
            "persistence_error",
        )

    def _weather_record(self) -> WeatherControlRecord | None:
        try:
            if self._weather_store is None:
                raise WeatherStateError("weather storage unavailable")
            return self._weather_store.load()
        except Exception:  # noqa: BLE001 - durable state boundary
            self._latch_persistence_failure()
            return None

    def _save_weather_record(self, record: WeatherControlRecord) -> bool:
        try:
            if self._weather_store is None:
                raise WeatherStateError("weather storage unavailable")
            self._weather_store.compare_and_swap(record.control_revision, record)
            return True
        except Exception:  # noqa: BLE001 - durable state boundary
            self._latch_persistence_failure()
            return False

    def _persist_weather_fault(self) -> None:
        # Preserve the marker even if the fault write fails: restart recovery
        # then still inhibits supply. Never recursively retry a failed disk.
        if (
            self._mode is not ControlMode.WEATHER_ASSISTED
            or self._weather_store is None
        ):
            return
        try:
            record = self._weather_store.load()
            self._weather_store.compare_and_swap(
                record.control_revision,
                replace(record, fault_inhibited=True, user_off=True),
            )
        except Exception:  # noqa: BLE001, S110 - marker is the durable fallback
            pass

    def _startup_weather(self) -> Decision:
        self._weather_started = False
        try:
            if (
                self._weather_store is None
                or self._weather_coordinator is None
                or self._weather_coordinator.store is not self._weather_store
            ):
                raise WeatherStateError("weather dependencies unavailable")
            self._weather_coordinator.invalidate("startup")
            record = self._weather_store.recover_interrupted()
            if record.active_marker is not None and not self._save_weather_record(
                replace(record, active_marker=None)
            ):
                return self._last_decision
        except Exception:  # noqa: BLE001 - startup must fail closed
            self._latch_persistence_failure()
            return self._last_decision
        self._weather_started = True
        # Startup requests a fresh fetch, but cannot consume a cached observation.
        return self._run_weather()

    def _weather_tick(self) -> WeatherEligibility | None:
        try:
            if self._weather_coordinator is None:
                raise WeatherStateError("weather coordinator unavailable")
            return self._weather_coordinator.tick()
        except Exception:  # noqa: BLE001 - coordinator/storage boundary
            self._latch_persistence_failure()
            return None

    def _run_weather(self) -> Decision:
        if self._is_faulted() or not self._weather_started:
            return self._last_decision
        record = self._weather_record()
        if record is None:
            return self._last_decision
        if record.fault_inhibited:
            self._best_effort_drain()
            return self._set_decision(
                Decision(
                    ControllerState.FAULT,
                    ActuatorCommand.DRAIN,
                    "weather_fault_inhibited",
                )
            )
        eligibility = self._weather_tick()
        if eligibility is None:
            return self._last_decision
        if self._timed_shower_monotonic_deadline is not None:
            if self._monotonic_clock() >= self._timed_shower_monotonic_deadline:
                return self._finish_timed_shower()
            return self._weather_supply("manual", "timed_shower_active")
        if record.user_off:
            return self._drain_weather("user_off", inhibit=False)
        if eligibility.eligible:
            return self._weather_supply("auto", "weather_eligible")
        return self._drain_weather(eligibility.reason, inhibit=False)

    def _weather_supply(self, marker: str, reason: str) -> Decision:
        record = self._weather_record()
        if record is None:
            return self._last_decision
        if record.user_off or record.fault_inhibited:
            return self._drain_weather("user_off", inhibit=False)
        action = (
            SupplyAction.RENEW
            if self._last_command is ActuatorCommand.SUPPLY
            else SupplyAction.BEGIN
        )
        if action is SupplyAction.BEGIN:
            if not self._save_weather_record(replace(record, active_marker=marker)):
                return self._last_decision
        elif record.active_marker != marker:
            self._best_effort_drain()
            return self._fault("weather_marker_mismatch")
        if not self._send(ActuatorCommand.SUPPLY, force=True, supply_action=action):
            self._best_effort_drain()
            return self._fault("relay_driver_error")
        return self._set_decision(
            Decision(
                ControllerState.TIMED_SHOWER
                if marker == "manual"
                else ControllerState.AUTO_SUPPLY,
                ActuatorCommand.SUPPLY,
                reason,
            )
        )

    def _drain_weather(self, reason: str, *, inhibit: bool) -> Decision:
        record = self._weather_record()
        if record is None:
            # An operator or shutdown may always retry DRAIN even while storage
            # is unavailable and a previous persistence failure is latched.
            self._send(ActuatorCommand.DRAIN, force=True, record_error=False)
            return self._last_decision
        if inhibit and not self._save_weather_record(replace(record, user_off=True)):
            return self._last_decision
        self._timed_shower_deadline = None
        self._timed_shower_monotonic_deadline = None
        self._timed_shower_duration_s = None
        if not self._send(
            ActuatorCommand.DRAIN,
            force=inhibit or self._last_command is not ActuatorCommand.DRAIN,
        ):
            return self._fault("relay_driver_error")
        record = self._weather_record()
        if record is None:
            return self._last_decision
        clear_marker = record.active_marker is not None or (
            self._is_faulted() and not record.fault_inhibited
        )
        if clear_marker and not self._save_weather_record(
            replace(
                record,
                active_marker=None,
                user_off=record.user_off or self._is_faulted(),
                fault_inhibited=record.fault_inhibited or self._is_faulted(),
            )
        ):
            return self._last_decision
        if self._is_faulted() or record.fault_inhibited:
            return self._last_decision
        return self._set_decision(
            Decision(ControllerState.MANUAL_DRAIN, ActuatorCommand.DRAIN, reason)
        )

    @staticmethod
    def _validate_weather_duration(duration_seconds: int) -> None:
        if (
            type(duration_seconds) is not int
            or not 60 <= duration_seconds <= 600
            or duration_seconds % 60
        ):
            raise ValueError("duration_seconds must be a whole minute from 60 to 600")

    def _start_weather_manual(self, duration_seconds: int) -> Decision:
        if self._is_faulted() or not self._weather_started:
            return self._last_decision
        record = self._weather_record()
        if record is None:
            return self._last_decision
        if record.user_off or record.fault_inhibited:
            return Decision(
                self._state, self._last_decision.command, "weather_start_required"
            )
        if self._timed_shower_monotonic_deadline is not None:
            if self._monotonic_clock() >= self._timed_shower_monotonic_deadline:
                return self._finish_timed_shower()
            return self._last_decision
        if duration_seconds > self._settings.timed_shower_max_s:
            return Decision(
                self._state,
                self._last_decision.command,
                "manual_duration_exceeds_settings_limit",
            )
        if self._last_command is ActuatorCommand.SUPPLY:
            self._drain_weather("manual_transition", inhibit=False)
            if self._is_faulted():
                return self._last_decision
        # Anchor before persistence/I/O so delays cannot gift extra manual time.
        deadline_mono = self._monotonic_clock() + duration_seconds
        deadline_wall = self._clock() + timedelta(seconds=duration_seconds)
        result = self._weather_supply("manual", "timed_shower_started")
        if result.state is ControllerState.TIMED_SHOWER:
            self._timed_shower_monotonic_deadline = deadline_mono
            self._timed_shower_deadline = deadline_wall
            self._timed_shower_duration_s = duration_seconds
        return result

    def start_weather_shower(self, duration_seconds: int) -> Decision:
        self._validate_weather_duration(duration_seconds)
        with self._lock:
            if self._mode is not ControlMode.WEATHER_ASSISTED:
                raise ValueError("weather action requires weather_assisted mode")
            if self._is_faulted() or not self._weather_started:
                return self._last_decision
            if self._timed_shower_monotonic_deadline is not None:
                return self._start_weather_manual(duration_seconds)
            record = self._weather_record()
            if record is None:
                return self._last_decision
            if record.fault_inhibited:
                return self._fault("weather_fault_inhibited")
            eligibility = self._weather_tick()
            if eligibility is None:
                return self._last_decision
            if (
                not eligibility.eligible
                and duration_seconds > self._settings.timed_shower_max_s
            ):
                return Decision(
                    self._state,
                    self._last_decision.command,
                    "manual_duration_exceeds_settings_limit",
                )
            if not self._save_weather_record(replace(record, user_off=False)):
                return self._last_decision
            if eligibility.eligible:
                return self._weather_supply("auto", "weather_eligible")
            return self._start_weather_manual(duration_seconds)

    def stop_weather_shower(self) -> Decision:
        with self._lock:
            if self._mode is not ControlMode.WEATHER_ASSISTED:
                raise ValueError("weather action requires weather_assisted mode")
            return self._drain_weather("user_off", inhibit=True)

    def _clear_weather_fault(self) -> Decision:
        if not self._is_faulted() or self._persistence_fault_latched:
            return self._last_decision
        if not self._send(ActuatorCommand.DRAIN, force=True):
            return self._last_decision
        record = self._weather_record()
        if record is None or not self._save_weather_record(
            replace(
                record,
                user_off=True,
                fault_inhibited=False,
                active_marker=None,
            )
        ):
            return self._last_decision
        return self._set_decision(
            Decision(ControllerState.MANUAL_DRAIN, ActuatorCommand.DRAIN, "user_off")
        )

    def update_weather_settings(
        self, expected_revision: int, settings: WeatherSettings
    ) -> WeatherSettings:
        with self._lock:
            try:
                if self._weather_coordinator is None:
                    raise WeatherStateError("weather coordinator unavailable")
                saved = self._weather_coordinator.update_settings(
                    expected_revision, settings
                )
            except WeatherRevisionConflict:
                raise
            except Exception as error:
                self._latch_persistence_failure()
                raise WeatherStateError("weather settings unavailable") from error
            if self._mode is ControlMode.WEATHER_ASSISTED:
                self._run_weather()
            return saved

    @contextmanager
    def weather_action_guard(
        self, expected_control_revision: int
    ) -> Iterator[WeatherControlRecord]:
        """Serialize W4 nonce/replay acceptance with control and settings changes.

        The caller validates/records its action under this guard, then invokes the
        reentrant service action. No awaits, network calls or worker joins here.
        Caller persistence failures must call handle_persistence_failure before
        leaving the guard. No other component may hold a lock while entering it.
        """
        with self._lock:
            if (
                self._mode is not ControlMode.WEATHER_ASSISTED
                or not self._weather_started
            ):
                raise WeatherRevisionConflict("weather controller not ready")
            record = self._weather_record()
            if record is None:
                raise WeatherStateError("weather state unavailable")
            if (
                type(expected_control_revision) is not int
                or record.control_revision != expected_control_revision
            ):
                raise WeatherRevisionConflict("weather control revision conflict")
            yield record

    def weather_status(self) -> WeatherControlStatus:
        """Never starts a fetch or SUPPLY; expiry and clock invalidation still apply."""
        with self._lock:
            self.status()  # Existing status semantics confirm DRAIN on manual expiry.
            record = self._weather_record()
            if record is None or self._weather_coordinator is None:
                raise WeatherStateError("weather state unavailable")
            operation = (
                "FAULT"
                if self._is_faulted() or record.fault_inhibited
                else "USER_OFF"
                if record.user_off
                else "MANUAL_ACTIVE"
                if self._timed_shower_monotonic_deadline is not None
                else "AUTO_SUPPLY"
                if self._state is ControllerState.AUTO_SUPPLY
                else "MANUAL_IDLE"
            )
            return WeatherControlStatus(
                record,
                operation,
                self._weather_coordinator.eligibility(record.settings),
                self._weather_coordinator.observation,
            )

    def shutdown(self) -> Decision:
        """Lifespan stops the loop first, then calls this, then stops the worker."""
        with self._lock:
            if self._mode is not ControlMode.WEATHER_ASSISTED:
                return self.drain("shutdown_drain")
            self._weather_started = False
            if self._weather_coordinator is not None:
                self._weather_coordinator.invalidate("shutdown")
            return self._drain_weather("shutdown_drain", inhibit=False)


class PeriodicControlLoop:
    def __init__(
        self,
        service: ControlService,
        *,
        cycle_interval_s: float = 30.0,
        forecast_interval_s: float = 3_600.0,
    ) -> None:
        self._service = service
        self._cycle_interval_s = (
            min(cycle_interval_s, WEATHER_PROCESSING_BOUND_SECONDS)
            if getattr(service, "mode", None) is ControlMode.WEATHER_ASSISTED
            else cycle_interval_s
        )
        self._forecast_interval_s = forecast_interval_s
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(
            target=self._run, name="freeze-protect-cycle", daemon=True
        )
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
