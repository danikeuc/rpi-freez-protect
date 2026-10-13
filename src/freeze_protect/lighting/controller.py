from __future__ import annotations

import math
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from .executor import Output, Receipt
from .models import (
    MAX_REVISION,
    Action,
    DurableState,
    Event,
    EventResult,
    Settings,
    SettingsUpdate,
    Status,
)
from .store import LightStore


class Clock(Protocol):
    def time(self) -> float: ...
    def monotonic(self) -> float: ...


class SystemClock:
    def time(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()


class LightError(Exception):
    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class LightController:
    """Serialized policy; an expired/faulted lease never starts itself again."""

    def __init__(
        self,
        database_path: Path,
        executor: Output,
        allowed_sources: set[str],
        clock: Clock | None = None,
        configured: bool = True,
        provision_new_database: bool = False,
    ) -> None:
        self.lock = threading.RLock()
        self.clock = clock or SystemClock()
        self.executor, self.allowed_sources = executor, allowed_sources
        self.configured = configured
        self.camera_until = self.dial_until = self.manual_until = 0.0
        self.desired_on = False
        self.gpio_on: bool | None = None
        self.health: Literal["OK", "FAULT", "UNAVAILABLE"] = (
            "OK" if configured else "UNAVAILABLE"
        )
        self.reason = "startup_off"
        self.receipt: Receipt | None = None
        self.executor_generation: str | None = None
        self.last_wall, self.last_mono = self.clock.time(), self.clock.monotonic()
        self.store: LightStore
        self.state = DurableState(
            revision=MAX_REVISION, settings=Settings(revision=MAX_REVISION)
        )
        checkpoint_loaded = loaded_state = False
        try:
            if not database_path.is_file():
                if not provision_new_database:
                    self.configured = False
                    raise OSError("lighting database requires explicit provisioning")
                LightStore.provision(database_path)
            self.store = LightStore(database_path)
            self.state = DurableState(
                revision=self.store.load_revision(),
                settings=Settings(revision=self.store.load_settings_revision()),
            )
            checkpoint_loaded = True
            loaded = self.store.load()
            if (
                loaded.revision != self.state.revision
                or loaded.settings.revision != self.state.settings.revision
            ):
                raise ValueError("state revision does not match durable fence")
            self.state = loaded
            loaded_state = True
            now = self.clock.time()
            if self.state.fault or (
                self.state.saved_at and now < self.state.saved_at - 5
            ):
                self.health, self.reason = "FAULT", "restart_clock_or_state_fault"
                self.state.fault = True
            elif self.state.mode != "AUTO" and self.state.manual_until > now:
                remaining = self.state.manual_until - now
                if remaining > 7200:
                    raise ValueError("invalid persisted deadline")
                self.state.mode = "MANUAL_OFF"
                self.manual_until = self.clock.monotonic() + remaining
                self.reason = "restart_manual_inhibited"
            else:
                self.state.mode, self.state.manual_until = "AUTO", 0.0
            self.state.boundary = max(now, self.state.boundary)
            self._revision()
            self._off()
            self._save("startup")
        except (OSError, sqlite3.Error, ValueError, OverflowError, LightError):
            if checkpoint_loaded and not loaded_state:
                self.state.settings.revision = min(
                    MAX_REVISION, self.state.settings.revision + 1
                )
            self._fault("startup_storage_or_executor_fault")

    def _stamp(self) -> str:
        return datetime.fromtimestamp(self.clock.time(), UTC).isoformat()

    def _revision(self) -> None:
        if self.state.revision >= MAX_REVISION:
            raise OSError("revision_exhausted")
        self.state.revision += 1

    def _save(
        self, source: str, record: tuple[str, str, str, dict[str, Any]] | None = None
    ) -> None:
        self.state.saved_at = self.clock.time()
        self.store.save(
            self.state,
            self.clock.time(),
            record,
            (self._stamp(), source, self.state.mode, self.desired_on, self.reason),
        )

    def _off(self) -> None:
        self.receipt = None
        self.executor_generation = None
        self.gpio_on = None
        receipt = self.executor.off()
        if receipt.command != "OFF" or receipt.gpio21 or receipt.lease_id is not None:
            raise OSError("uncertain OFF receipt")
        self.gpio_on = False
        self.executor_generation = receipt.generation

    def _fault(self, reason: str) -> None:
        self.desired_on = False
        self.camera_until = self.dial_until = 0.0
        self.state.fault = True
        self.health = "FAULT" if self.configured else "UNAVAILABLE"
        self.reason = reason
        self.state.boundary = max(self.state.boundary, self.clock.time())
        self.state.revision = min(MAX_REVISION, self.state.revision + 1)
        try:
            self._off()
        except (OSError, sqlite3.Error, ValueError, OverflowError, LightError):
            self.gpio_on = None
        if hasattr(self, "store"):
            try:
                self._save("fault")
            except (OSError, sqlite3.Error, ValueError, OverflowError, LightError):
                self.reason = reason + "_not_durable"

    def _check_clock(self) -> None:
        wall, mono = self.clock.time(), self.clock.monotonic()
        if not math.isfinite(wall) or not math.isfinite(mono):
            raise OSError("invalid clock")
        old_wall, old_mono = self.last_wall, self.last_mono
        self.last_wall, self.last_mono = wall, mono
        if mono < old_mono or abs((wall - old_wall) - (mono - old_mono)) > 5:
            raise OSError("clock discontinuity")

    def status(self) -> Status:
        with self.lock:
            now = self.clock.monotonic()
            manual = (
                max(0, math.ceil(self.manual_until - now))
                if self.state.mode != "AUTO"
                else 0
            )
            remain = (
                manual
                if self.state.mode != "AUTO"
                else max(0, math.ceil(max(self.camera_until, self.dial_until) - now))
            )
            return Status(
                revision=self.state.revision,
                mode=self.state.mode,
                desired_on=self.desired_on,
                gpio_on=self.gpio_on,
                health=self.health,
                reason=self.reason,
                remaining_seconds=remain,
                manual_remaining_seconds=manual,
                observed_at=self._stamp(),
            )

    def settings(self) -> Settings:
        with self.lock:
            return self.state.settings.model_copy()

    def _lookup(
        self, kind: str, identity: str, fingerprint: str
    ) -> dict[str, Any] | None:
        if not hasattr(self, "store"):
            raise OSError("lighting storage unavailable")
        result = self.store.lookup(kind, identity)
        if result:
            if result[0] != fingerprint:
                raise LightError(409, "identity_reused")
            recorded_status = result[1].get("status", result[1])
            if (
                isinstance(recorded_status, dict)
                and recorded_status.get("reason") == "intent_unconfirmed"
            ):
                raise LightError(503, "light_fault")
            return result[1]
        return None

    def _output(self) -> None:
        if not self.desired_on:
            self._off()
            return
        receipt = self.executor.begin()
        if (
            receipt.command != "ON"
            or not receipt.gpio21
            or not receipt.lease_id
            or receipt.generation != self.executor_generation
        ):
            raise OSError("uncertain ON receipt")
        self.receipt, self.gpio_on = receipt, True

    def _commit_intent(
        self, kind: str, identity: str, fingerprint: str, accepted: bool = True
    ) -> Status | EventResult:
        self._revision()
        # Persist replay identity BEFORE an output can energize. A crash retains an
        # uncertain outcome and restart cannot replay that intent.
        self.gpio_on = None
        provisional = self.status().model_copy(
            update={"health": "FAULT", "reason": "intent_unconfirmed"}
        )
        result: Status | EventResult = (
            EventResult(accepted=accepted, duplicate=False, status=provisional)
            if kind == "event"
            else provisional
        )
        self._save(kind, (kind, identity, fingerprint, result.model_dump()))
        self._output()
        result = (
            EventResult(accepted=accepted, duplicate=False, status=self.status())
            if kind == "event"
            else self.status()
        )
        self._save(kind, (kind, identity, fingerprint, result.model_dump()))
        return result

    def _expire(self) -> bool:
        now = self.clock.monotonic()
        if self.health != "OK":
            return False
        if self.state.mode != "AUTO" and now >= self.manual_until:
            self.state.mode, self.state.manual_until, self.manual_until = (
                "AUTO",
                0.0,
                0.0,
            )
            self.camera_until = self.dial_until = 0.0
            self.state.boundary = self.clock.time()
            self.reason = "manual_expired"
        elif (
            self.state.mode == "AUTO"
            and self.desired_on
            and now >= max(self.camera_until, self.dial_until)
        ):
            self.reason = "hold_expired"
        else:
            return False
        self.desired_on = False
        self._revision()
        self._save("expiry")
        self._off()
        return True

    def actions(self, request: Action) -> Status:
        with self.lock:
            try:
                fingerprint = request.model_dump_json()
                previous = self._lookup("action", request.request_id, fingerprint)
                if previous:
                    return Status.model_validate(previous)
                self._check_clock()
                self._expire()
                if request.expected_revision != self.state.revision:
                    raise LightError(409, "stale_revision")
                if request.action not in {"off", "auto"} and self.health != "OK":
                    raise LightError(503, "light_unavailable")
                if request.action != "timed_on":
                    self.camera_until = self.dial_until = 0.0
                now = self.clock.monotonic()
                if request.action == "timed_on":
                    if self.state.mode == "AUTO":
                        self.dial_until = now + self.state.settings.hold_seconds
                        self.desired_on = True
                    else:
                        self.state.mode = "MANUAL_ON"
                        self.manual_until = now + self.state.settings.manual_seconds
                        self.state.manual_until = (
                            self.clock.time() + self.state.settings.manual_seconds
                        )
                        self.desired_on = True
                elif request.action in {"manual_on", "manual_off"} or (
                    request.action == "off" and self.state.mode != "AUTO"
                ):
                    self.state.mode = (
                        "MANUAL_ON" if request.action == "manual_on" else "MANUAL_OFF"
                    )
                    self.manual_until = now + self.state.settings.manual_seconds
                    self.state.manual_until = (
                        self.clock.time() + self.state.settings.manual_seconds
                    )
                    self.desired_on = self.state.mode == "MANUAL_ON"
                    self.state.boundary = self.clock.time()
                else:
                    self.desired_on = False
                    self.state.boundary = self.clock.time()
                    if request.action == "auto":
                        self._off()  # Fresh OFF receipt required to clear a latched fault.
                        if not self.configured:
                            raise LightError(503, "light_unconfigured")
                        self.state.mode, self.state.manual_until, self.manual_until = (
                            "AUTO",
                            0.0,
                            0.0,
                        )
                        self.state.fault, self.health = False, "OK"
                        self.last_wall, self.last_mono = self.clock.time(), now
                self.reason = request.action
                result = self._commit_intent("action", request.request_id, fingerprint)
                assert isinstance(result, Status)
                return result
            except LightError:
                raise
            except (OSError, sqlite3.Error, ValueError, OverflowError):
                self._fault("action_storage_or_output_fault")
                raise LightError(503, "light_fault") from None

    def events(self, request: Event) -> EventResult:
        with self.lock:
            try:
                fingerprint = request.model_dump_json()
                previous = self._lookup("event", request.event_id, fingerprint)
                if previous:
                    return EventResult.model_validate(previous).model_copy(
                        update={"duplicate": True}
                    )
                self._check_clock()
                self._expire()
                if request.source_id not in self.allowed_sources:
                    raise LightError(403, "source_not_allowed")
                age = self.clock.time() - request.timestamp
                if age > 60 or age < -5:
                    raise LightError(422, "event_time_invalid")
                accepted = (
                    self.health == "OK"
                    and self.state.mode == "AUTO"
                    and request.timestamp > self.state.boundary
                )
                if accepted:
                    self.camera_until = (
                        self.clock.monotonic() + self.state.settings.hold_seconds
                    )
                    self.desired_on = True
                    self.reason = "camera_hold"
                    result = self._commit_intent("event", request.event_id, fingerprint)
                    assert isinstance(result, EventResult)
                    return result
                result = EventResult(
                    accepted=False, duplicate=False, status=self.status()
                )
                self._save(
                    "event",
                    ("event", request.event_id, fingerprint, result.model_dump()),
                )
                return result
            except LightError:
                raise
            except OverflowError:
                self._fault("identity_capacity")
                raise LightError(429, "identity_capacity") from None
            except (OSError, sqlite3.Error, ValueError):
                self._fault("event_storage_or_output_fault")
                raise LightError(503, "light_fault") from None

    def update_settings(self, request: SettingsUpdate) -> Settings:
        with self.lock:
            try:
                fingerprint = request.model_dump_json()
                previous = self._lookup("settings", request.request_id, fingerprint)
                if previous:
                    return Settings.model_validate(previous)
                if request.expected_revision != self.state.settings.revision:
                    raise LightError(409, "stale_settings_revision")
                settings = Settings(
                    revision=self.state.settings.revision + 1,
                    hold_seconds=request.hold_seconds,
                    manual_seconds=request.manual_seconds,
                )
                self.state.settings = settings
                self._save(
                    "settings",
                    (
                        "settings",
                        request.request_id,
                        fingerprint,
                        settings.model_dump(),
                    ),
                )
                return settings.model_copy()
            except LightError:
                raise
            except (OSError, sqlite3.Error, ValueError, OverflowError):
                self._fault("settings_storage_fault")
                raise LightError(503, "light_fault") from None

    def history(self, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        if not 1 <= limit <= 100 or not 0 <= offset <= 1000000:
            raise LightError(422, "history_bounds")
        with self.lock:
            try:
                if not hasattr(self, "store"):
                    raise OSError("lighting storage unavailable")
                return {
                    "items": self.store.history(limit, offset),
                    "limit": limit,
                    "offset": offset,
                }
            except (OSError, sqlite3.Error, ValueError, OverflowError, LightError):
                self._fault("history_storage_fault")
                raise LightError(503, "light_fault") from None

    def tick(self) -> None:
        with self.lock:
            try:
                self._check_clock()
                if self._expire() or self.health != "OK" or not self.desired_on:
                    return
                receipt = self.executor.renew()
                if (
                    not self.receipt
                    or receipt.generation != self.receipt.generation
                    or receipt.lease_id != self.receipt.lease_id
                    or not receipt.gpio21
                    or receipt.command != "ON"
                ):
                    raise OSError("uncertain renewal")
                self.gpio_on = True
            except (OSError, sqlite3.Error, ValueError, OverflowError, LightError):
                self._fault("clock_or_lease_fault")

    def close(self) -> None:
        with self.lock:
            self.desired_on = False
            try:
                self._off()
            finally:
                if hasattr(self, "store"):
                    self.store.close()
