"""Serialized, durable admission for deliberate display weather actions."""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass
from math import isfinite
from uuid import UUID

from freeze_protect.application.service import ControlService
from freeze_protect.domain.models import ActuatorCommand, ControllerState, ControlMode
from freeze_protect.persistence.weather import (
    SQLiteWeatherStore,
    WeatherActionReceipt,
    WeatherStateError,
)

MAX_WIRE_REVISION = 9_007_199_254_740_991
NONCE_SECONDS = 10.0


class WeatherActionError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class WeatherActionInput:
    request_id: str
    expected_control_revision: int
    action_nonce: str
    duration_seconds: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str):
            raise TypeError("request_id must be a UUID")
        try:
            valid_uuid = str(UUID(self.request_id)) == self.request_id.lower()
        except ValueError as error:
            raise ValueError("request_id must be a UUID") from error
        if not valid_uuid:
            raise ValueError("request_id must be a UUID")
        if type(self.expected_control_revision) is not int or not (
            0 <= self.expected_control_revision <= MAX_WIRE_REVISION
        ):
            raise ValueError("invalid control revision")
        if (
            not isinstance(self.action_nonce, str)
            or not 1 <= len(self.action_nonce) <= 128
        ):
            raise ValueError("invalid action nonce")
        if self.duration_seconds is not None and (
            type(self.duration_seconds) is not int
            or not 60 <= self.duration_seconds <= 600
            or self.duration_seconds % 60
        ):
            raise ValueError("duration must be whole minutes from 60 to 600 seconds")


@dataclass(frozen=True, slots=True)
class WeatherActionResult:
    request_id: str
    accepted: bool
    control_revision: int
    status: dict[str, object]


class WeatherActionGate:
    """Service RLock owns all nonce, receipt and admission state; no outer lock."""

    def __init__(
        self,
        service: ControlService,
        store: SQLiteWeatherStore,
        status_payload: Callable[[bool], dict[str, object]],
        monotonic_clock: Callable[[], float],
    ) -> None:
        self._service = service
        self._store = store
        self._status_payload = status_payload
        self._clock = monotonic_clock
        self._nonces: dict[str, tuple[int, float]] = {}
        store.initialize_action_receipts()

    def recover_pending(self) -> None:
        with self._service.weather_action_guard():
            try:
                if self._store.reconcile_pending_action_receipts():
                    self._service.handle_persistence_failure()
            except WeatherStateError:
                self._service.handle_persistence_failure()
                raise

    def _nonce(self, revision: int) -> str | None:
        now = self._clock()
        self._nonces = {
            key: (bound, issued)
            for key, (bound, issued) in self._nonces.items()
            if bound == revision
            and isfinite(now - issued)
            and 0 <= now - issued < NONCE_SECONDS
        }
        if not isfinite(now) or len(self._nonces) >= 64:
            return None
        nonce = secrets.token_urlsafe(32)
        self._nonces[nonce] = (revision, now)
        return nonce

    def _snapshot(self, *, read_only: bool) -> dict[str, object]:
        payload = self._status_payload(read_only)
        revision = payload.get("control_revision")
        if type(revision) is not int or not 0 <= revision <= MAX_WIRE_REVISION:
            raise WeatherStateError("weather revision outside wire range")
        payload["action_nonce"] = (
            self._nonce(revision)
            if self._service.mode is ControlMode.WEATHER_ASSISTED
            else None
        )
        return payload

    def status(self) -> dict[str, object]:
        with self._service.weather_action_guard():
            return self._snapshot(read_only=False)

    def execute(self, action: str, request: WeatherActionInput) -> WeatherActionResult:
        if action not in ("start", "stop") or (
            action == "stop" and request.duration_seconds is not None
        ):
            raise WeatherActionError(422, "invalid weather action")
        with self._service.weather_action_guard():
            try:
                return self._execute(action, request)
            except WeatherStateError as error:
                self._service.handle_persistence_failure()
                raise WeatherActionError(
                    503, "weather action storage unavailable"
                ) from error

    def _execute(self, action: str, request: WeatherActionInput) -> WeatherActionResult:
        encoded = json.dumps(
            {"action": action, **asdict(request)}, sort_keys=True, allow_nan=False
        )
        body_hash = hashlib.sha256(encoded.encode()).hexdigest()
        previous = self._store.get_action_receipt(request.request_id)
        if previous is not None:
            if previous.body_hash != body_hash:
                raise WeatherActionError(
                    409, "request_id was used for a different action"
                )
            return self._result(previous)
        current = self._snapshot(read_only=False)
        if current["control_revision"] != request.expected_control_revision:
            raise WeatherActionError(409, "weather control revision conflict")
        if current.get("operation") == "FAULT" and action == "start":
            raise WeatherActionError(409, "weather controller is fault inhibited")
        nonce = self._nonces.get(request.action_nonce)
        now = self._clock()
        if (
            nonce is None
            or nonce[0] != request.expected_control_revision
            or not (isfinite(now - nonce[1]) and 0 <= now - nonce[1] < NONCE_SECONDS)
        ):
            raise WeatherActionError(409, "weather action nonce expired or invalid")
        with self._service.weather_action_guard(request.expected_control_revision):
            del self._nonces[request.action_nonce]
            self._store.begin_action_receipt(request.request_id, body_hash)
            try:
                decision = (
                    self._service.start_weather_shower(
                        request.duration_seconds
                        if request.duration_seconds is not None
                        else self._service.settings.timed_shower_default_s
                    )
                    if action == "start"
                    else self._service.stop_weather_shower()
                )
            except Exception as error:
                self._service.handle_persistence_failure()
                raise WeatherActionError(
                    503, "weather action outcome unknown"
                ) from error
            failure: WeatherActionError | None = None
            if decision.state is ControllerState.FAULT:
                failure = WeatherActionError(503, "weather controller unavailable")
            elif action == "start" and decision.command is not ActuatorCommand.SUPPLY:
                failure = WeatherActionError(409, "weather start not accepted")
            elapsed = self._clock() - nonce[1]
            if not isfinite(elapsed) or not 0 <= elapsed < NONCE_SECONDS:
                self._service.handle_persistence_failure()
                failure = WeatherActionError(503, "weather action response expired")
            revision = self._store.load().control_revision
            receipt = self._store.finish_action_receipt(
                request.request_id,
                revision,
                error_status=failure.status_code if failure else None,
                error_reason=failure.detail if failure else None,
            )
            result = self._result(receipt)
            elapsed = self._clock() - nonce[1]
            if not isfinite(elapsed) or not 0 <= elapsed < NONCE_SECONDS:
                self._service.handle_persistence_failure()
                self._store.mark_action_unknown(request.request_id)
                raise WeatherActionError(503, "weather action response expired")
            return result

    def _result(self, receipt: WeatherActionReceipt) -> WeatherActionResult:
        if receipt.state != "success" or receipt.control_revision is None:
            raise WeatherActionError(
                receipt.error_status or 503,
                receipt.error_reason or "weather action outcome unknown",
            )
        return WeatherActionResult(
            receipt.request_id,
            True,
            receipt.control_revision,
            self._snapshot(read_only=True),
        )
