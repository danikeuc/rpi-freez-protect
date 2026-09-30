from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime, timedelta

from freeze_protect.application.ports import AdapterError, TemperatureSource
from freeze_protect.application.temperature_telemetry import (
    DISPLAY_TEMPERATURE_SAMPLE_INTERVAL_S,
    DISPLAY_TEMPERATURE_STALE_AFTER_S,
    TemperatureTelemetrySampler,
)
from freeze_protect.domain.models import SensorHealth, TemperatureReading

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class FakeTemperatureSource:
    def __init__(self, *results: TemperatureReading | Exception) -> None:
        self.results = list(results)
        self.calls = 0
        self._lock = threading.Lock()
        self.active_reads = 0
        self.max_active_reads = 0
        self.read_delay_s = 0.0
        self.read_started = threading.Event()

    def read(self) -> TemperatureReading:
        with self._lock:
            self.calls += 1
            self.active_reads += 1
            self.max_active_reads = max(self.max_active_reads, self.active_reads)
            index = min(self.calls - 1, len(self.results) - 1)
            result = self.results[index]
        self.read_started.set()
        try:
            if self.read_delay_s:
                time.sleep(self.read_delay_s)
            if isinstance(result, Exception):
                raise result
            return result
        finally:
            with self._lock:
                self.active_reads -= 1


def reading(
    value: float | None,
    health: SensorHealth = SensorHealth.HEALTHY,
    observed_at: datetime = NOW,
) -> TemperatureReading:
    return TemperatureReading(value, observed_at, health)


def make_sampler(
    source: TemperatureSource, clock: MutableClock | None = None
) -> TemperatureTelemetrySampler:
    return TemperatureTelemetrySampler(source, clock=clock or MutableClock())


def test_initial_snapshot_is_unavailable_and_timestamped_at_construction() -> None:
    clock = MutableClock()
    sampler = make_sampler(FakeTemperatureSource(reading(7.0)), clock)

    assert sampler.snapshot() == reading(None, SensorHealth.STALE)
    assert sampler.snapshot().observed_at == NOW


def test_sample_once_caches_healthy_reading_and_snapshot_stales_at_threshold() -> None:
    clock = MutableClock()
    sampler = TemperatureTelemetrySampler(
        FakeTemperatureSource(reading(7.0)), clock=clock
    )

    assert sampler.sample_once() == reading(7.0)
    clock.value = NOW + timedelta(seconds=DISPLAY_TEMPERATURE_STALE_AFTER_S - 0.001)
    assert sampler.snapshot() == reading(7.0)
    clock.value = NOW + timedelta(seconds=DISPLAY_TEMPERATURE_STALE_AFTER_S)
    assert sampler.snapshot() == reading(None, SensorHealth.STALE)


def test_non_healthy_samples_never_expose_a_numeric_value() -> None:
    for health in (
        SensorHealth.INVALID,
        SensorHealth.STALE,
        SensorHealth.CALIBRATION_REQUIRED,
    ):
        sampler = make_sampler(FakeTemperatureSource(reading(12.0, health)))

        result = sampler.sample_once()

        assert result == reading(None, health)
        assert sampler.snapshot() == reading(None, health)


def test_non_healthy_sample_replaces_prior_numeric_value() -> None:
    sampler = make_sampler(
        FakeTemperatureSource(
            reading(7.0), reading(99.0, SensorHealth.INVALID)
        )
    )

    assert sampler.sample_once() == reading(7.0)
    assert sampler.sample_once() == reading(None, SensorHealth.INVALID)
    assert sampler.snapshot().value_c is None


def test_future_dated_healthy_reading_is_unavailable() -> None:
    sampler = make_sampler(
        FakeTemperatureSource(reading(7.0, observed_at=NOW + timedelta(seconds=1)))
    )

    result = sampler.sample_once()

    assert result == reading(None, SensorHealth.STALE, NOW + timedelta(seconds=1))
    assert sampler.snapshot() == result


def test_future_dated_non_healthy_reading_is_stale() -> None:
    future = NOW + timedelta(seconds=1)
    sampler = make_sampler(
        FakeTemperatureSource(
            reading(7.0, SensorHealth.INVALID, observed_at=future)
        )
    )

    assert sampler.sample_once() == reading(None, SensorHealth.STALE, future)


def test_start_samples_immediately_and_repeated_start_does_not_start_another_thread() -> None:
    source = FakeTemperatureSource(reading(7.0))
    source.read_delay_s = 0.005
    sampler = TemperatureTelemetrySampler(
        source, clock=MutableClock(), sample_interval_s=0.02
    )

    sampler.start()
    assert source.read_started.wait(timeout=0.5)
    sampler.start()
    time.sleep(0.055)
    sampler.stop()

    assert source.calls >= 2
    assert source.max_active_reads == 1


def test_worker_survives_adapter_and_unexpected_exceptions(caplog: object) -> None:
    source = FakeTemperatureSource(
        AdapterError("private adapter details"),
        RuntimeError("private unexpected details"),
        reading(8.0),
    )
    sampler = TemperatureTelemetrySampler(
        source, clock=MutableClock(), sample_interval_s=0.01
    )

    with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
        sampler.start()
        deadline = time.monotonic() + 0.5
        while source.calls < 3 and time.monotonic() < deadline:
            time.sleep(0.005)
        sampler.stop()

    assert source.calls >= 3
    assert sampler.snapshot() == reading(8.0)
    assert "private adapter details" not in caplog.text  # type: ignore[attr-defined]
    assert "private unexpected details" not in caplog.text  # type: ignore[attr-defined]


def test_sample_failure_returns_fixed_stale_snapshot(caplog: object) -> None:
    sampler = make_sampler(FakeTemperatureSource(AdapterError("private detail")))

    with caplog.at_level(logging.WARNING):  # type: ignore[attr-defined]
        result = sampler.sample_once()

    assert result == reading(None, SensorHealth.STALE)
    assert "private detail" not in caplog.text  # type: ignore[attr-defined]


def test_stop_is_repeatable_and_restart_after_stop_is_unsupported() -> None:
    source = FakeTemperatureSource(reading(7.0))
    sampler = TemperatureTelemetrySampler(
        source, clock=MutableClock(), sample_interval_s=0.01
    )

    sampler.start()
    assert source.read_started.wait(timeout=0.5)
    sampler.stop()
    stopped_calls = source.calls
    sampler.stop()
    sampler.start()
    time.sleep(0.03)

    assert source.calls == stopped_calls


def test_default_intervals_match_display_contract() -> None:
    assert DISPLAY_TEMPERATURE_SAMPLE_INTERVAL_S == 5.0
    assert DISPLAY_TEMPERATURE_STALE_AFTER_S == 15.0
