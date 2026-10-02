"""One outstanding daemon fetch; polling owns deadline expiry and result acceptance."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from threading import Lock, Thread
from time import monotonic

from freeze_protect.domain.weather import (
    WEATHER_FETCH_DEADLINE_SECONDS,
    WeatherSettings,
    WeatherWindow,
)


@dataclass(frozen=True, slots=True)
class WeatherRequest:
    settings: WeatherSettings
    requested_at: datetime
    generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.settings, WeatherSettings):
            raise TypeError("settings must be WeatherSettings")
        if (
            not isinstance(self.requested_at, datetime)
            or self.requested_at.utcoffset() is None
        ):
            raise ValueError("requested_at must be timezone aware")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class WeatherResult:
    request: WeatherRequest
    window: WeatherWindow | None
    error: str | None
    started_mono: float


Fetch = Callable[[WeatherSettings, datetime, int], WeatherWindow]


class WeatherWorker:
    """Never replace a live fetch thread, even after cancellation or expiry.

    Control must poll regularly and cancel when settings/generation change. A stuck
    transport cannot be forcibly killed; it holds the only slot until it exits.
    No network, database or actuator work is done by the notification callback.
    """

    def __init__(
        self,
        fetch: Fetch,
        wake: Callable[[], None],
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._fetch = fetch
        self._wake = wake
        self._clock = monotonic_clock
        self._lock = Lock()
        self._thread: Thread | None = None
        self._request: WeatherRequest | None = None
        self._result: WeatherResult | None = None
        self._started = 0.0
        self._discard = False
        self._stopped = False
        self._generation = -1

    def submit(self, request: WeatherRequest) -> bool:
        with self._lock:
            if (
                self._stopped
                or self._request is not None
                or (self._thread is not None and self._thread.is_alive())
                or request.generation < self._generation
            ):
                return False
            self._request = request
            self._started = self._clock()
            self._discard = False
            self._generation = request.generation
            self._thread = Thread(
                target=self._run,
                args=(request,),
                daemon=True,
                name="freeze-protect-weather",
            )
            try:
                self._thread.start()
            except RuntimeError:
                self._request = None
                self._thread = None
                raise
            return True

    def _expired(self) -> bool:
        elapsed = self._clock() - self._started
        return (
            not isfinite(elapsed)
            or elapsed < 0
            or elapsed >= WEATHER_FETCH_DEADLINE_SECONDS
        )

    def poll(self) -> WeatherResult | None:
        with self._lock:
            request = self._request
            if request is None or self._discard:
                return None
            if self._expired():
                self._discard = True
                self._request = None
                self._result = None
                return WeatherResult(request, None, "deadline_exceeded", self._started)
            result = self._result
            if result is not None:
                self._result = None
                self._request = None
            return result

    def cancel(self) -> None:
        """Discard the current generation without waiting for its transport."""
        with self._lock:
            self._discard = True
            self._request = None
            self._result = None

    def stop(self, timeout_s: float = 1.0) -> None:
        if isinstance(timeout_s, bool) or not isfinite(timeout_s) or timeout_s < 0:
            raise ValueError("shutdown timeout must be finite and nonnegative")
        with self._lock:
            self._stopped = True
            self._discard = True
            self._request = None
            self._result = None
            thread = self._thread
        if thread is not None:
            thread.join(min(timeout_s, 1.0))

    def _run(self, request: WeatherRequest) -> None:
        try:
            window = self._fetch(
                request.settings, request.requested_at, request.generation
            )
            if (
                not isinstance(window, WeatherWindow)
                or window.generation != request.generation
                or window.settings_revision != request.settings.revision
                or window.timezone != request.settings.timezone
                or window.requested_latitude != request.settings.latitude
                or window.requested_longitude != request.settings.longitude
                or window.fetched_at != request.requested_at
            ):
                result = WeatherResult(
                    request, None, "provenance_mismatch", self._started
                )
            else:
                result = WeatherResult(request, window, None, self._started)
        except Exception:  # noqa: BLE001 - injected fetch failure boundary
            # Transport implementation failures must become sanitized failed attempts.
            result = WeatherResult(request, None, "fetch_failed", self._started)
        with self._lock:
            if not self._discard and not self._stopped:
                self._result = (
                    WeatherResult(request, None, "deadline_exceeded", self._started)
                    if self._expired()
                    else result
                )
        try:
            self._wake()
        except Exception:  # noqa: BLE001, S110 - polling remains authoritative
            # Notification failure cannot turn a failed fetch into a success or
            # strand the lock. Control polling remains authoritative.
            pass
