from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
        self.second_read_started = threading.Event()
        self.read_release: threading.Event | None = None

    def read(self) -> TemperatureReading:
        with self._lock:
            self.calls += 1
            self.active_reads += 1
            self.max_active_reads = max(self.max_active_reads, self.active_reads)
            index = min(self.calls - 1, len(self.results) - 1)
            result = self.results[index]
            if self.calls == 2:
                self.second_read_started.set()
        self.read_started.set()
        try:
            if self.read_release is not None:
                self.read_release.wait()
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


def test_blocked_read_does_not_block_stale_snapshot() -> None:
    clock = MutableClock()
    source = FakeTemperatureSource(reading(7.0))
    sampler = make_sampler(source, clock)
    assert sampler.sample_once() == reading(7.0)
    source.read_started.clear()
    source.read_release = threading.Event()
    sampler.start()

    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            assert source.read_started.wait(timeout=0.5)
            clock.value = NOW + timedelta(seconds=15)

            snapshot = executor.submit(sampler.snapshot).result(timeout=0.5)

            assert snapshot == reading(None, SensorHealth.STALE)
            assert not source.read_release.is_set()
        finally:
            source.read_release.set()
            sampler.stop()


def test_stop_signals_and_returns_while_source_read_is_blocked() -> None:
    source = FakeTemperatureSource(reading(7.0))
    source.read_release = threading.Event()
    sampler = TemperatureTelemetrySampler(
        source, clock=MutableClock(), sample_interval_s=0.01
    )
    sampler.start()
    worker = sampler._thread
    assert worker is not None

    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            assert source.read_started.wait(timeout=0.5)
            stopped = executor.submit(sampler.stop)

            assert sampler._stop_event.wait(timeout=0.5)
            stopped.result(timeout=1.5)
            assert worker.is_alive()
            assert worker.daemon
            assert not source.read_release.is_set()
            sampler.start()
            assert sampler._thread is worker
        finally:
            source.read_release.set()
            sampler.stop()
            worker.join(timeout=0.5)

    assert not worker.is_alive()
    assert source.calls == 1
    sampler.stop()
    sampler.start()
    assert sampler._thread is worker
    assert not worker.is_alive()


def test_concurrent_sample_once_calls_keep_source_reads_exclusive() -> None:
    source = FakeTemperatureSource(reading(7.0))
    source.read_release = threading.Event()
    sampler = make_sampler(source)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(sampler.sample_once)
        try:
            assert source.read_started.wait(timeout=0.5)
            second = executor.submit(sampler.sample_once)
            assert not source.second_read_started.wait(timeout=0.1)
        finally:
            source.read_release.set()
        assert first.result(timeout=0.5) == reading(7.0)
        assert second.result(timeout=0.5) == reading(7.0)

    assert source.calls == 2
    assert source.max_active_reads == 1


def test_queued_sample_does_not_read_source_after_stop() -> None:
    source = FakeTemperatureSource(reading(7.0))
    source.read_release = threading.Event()
    sampler = make_sampler(source)
    second_started = threading.Event()

    def queued_sample() -> TemperatureReading:
        second_started.set()
        return sampler.sample_once()

    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(sampler.sample_once)
        try:
            assert source.read_started.wait(timeout=0.5)
            second = executor.submit(queued_sample)
            assert second_started.wait(timeout=0.5)

            executor.submit(sampler.stop).result(timeout=0.5)
            assert not source.second_read_started.is_set()
        finally:
            source.read_release.set()
        assert first.result(timeout=0.5) == reading(7.0)
        assert second.result(timeout=0.5) == reading(7.0)

    assert source.calls == 1
