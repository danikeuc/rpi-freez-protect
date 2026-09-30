from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime

from freeze_protect.application.ports import AdapterError, TemperatureSource
from freeze_protect.domain.models import SensorHealth, TemperatureReading

DISPLAY_TEMPERATURE_SAMPLE_INTERVAL_S = 5.0
DISPLAY_TEMPERATURE_STALE_AFTER_S = 15.0
DISPLAY_TEMPERATURE_STOP_TIMEOUT_S = 1.0

_LOGGER = logging.getLogger(__name__)


class TemperatureTelemetrySampler:
    """Periodically cache a temperature reading for display consumers."""

    def __init__(
        self,
        source: TemperatureSource,
        *,
        clock: Callable[[], datetime],
        sample_interval_s: float = DISPLAY_TEMPERATURE_SAMPLE_INTERVAL_S,
        stale_after_s: float = DISPLAY_TEMPERATURE_STALE_AFTER_S,
    ) -> None:
        if sample_interval_s <= 0:
            raise ValueError("sample_interval_s must be positive")
        if stale_after_s < 0:
            raise ValueError("stale_after_s must not be negative")

        self._source = source
        self._clock = clock
        self._sample_interval_s = sample_interval_s
        self._stale_after_s = stale_after_s
        self._lock = threading.Lock()
        self._read_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._snapshot = TemperatureReading(None, clock(), SensorHealth.STALE)
        self._thread: threading.Thread | None = None
        self._stopped = False

    def start(self) -> None:
        with self._lock:
            if self._thread is not None or self._stopped:
                return
            self._thread = threading.Thread(
                target=self._run,
                name="temperature-display-sampler",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            self._stop_event.set()
            thread = self._thread
        if thread is not None:
            # A stuck sensor must not prevent the caller's final DRAIN cleanup.
            thread.join(timeout=DISPLAY_TEMPERATURE_STOP_TIMEOUT_S)
            if thread.is_alive():
                _LOGGER.warning("temperature sampler stop timed out")

    def sample_once(self) -> TemperatureReading:
        # Serialize source reads without holding up cache access or stop signals.
        with self._read_lock:
            if self._stop_event.is_set():
                return self.snapshot()
            try:
                reading = self._source.read()
            except AdapterError:
                _LOGGER.warning("temperature sample failed: adapter error")
                reading = TemperatureReading(None, self._clock(), SensorHealth.STALE)
            except Exception:  # noqa: BLE001 - keep the display sampler alive.
                _LOGGER.warning("temperature sample failed: unexpected error")
                reading = TemperatureReading(None, self._clock(), SensorHealth.STALE)
            else:
                now = self._clock()
                if reading.observed_at > now:
                    reading = TemperatureReading(
                        None, reading.observed_at, SensorHealth.STALE
                    )
                elif reading.health is not SensorHealth.HEALTHY:
                    reading = TemperatureReading(
                        None, reading.observed_at, reading.health
                    )
            with self._lock:
                self._snapshot = reading
            return reading

    def snapshot(self) -> TemperatureReading:
        with self._lock:
            reading = self._snapshot
        if reading.health is not SensorHealth.HEALTHY:
            return reading

        now = self._clock()
        age_s = (now - reading.observed_at).total_seconds()
        if age_s < 0 or age_s >= self._stale_after_s:
            return TemperatureReading(None, reading.observed_at, SensorHealth.STALE)
        return reading

    def _run(self) -> None:
        while not self._stop_event.is_set():
            sample_started = time.monotonic()
            self.sample_once()
            remaining_s = self._sample_interval_s - (
                time.monotonic() - sample_started
            )
            if self._stop_event.wait(max(0.0, remaining_s)):
                return
