from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from threading import Event, current_thread
from time import monotonic

import pytest

from freeze_protect.application.weather_worker import WeatherRequest, WeatherWorker
from freeze_protect.domain.weather import WeatherSettings, WeatherWindow

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
SETTINGS = WeatherSettings(True, 46.5, 15.5)


def window(request):
    return WeatherWindow(
        tuple(NOW.date() + timedelta(days=i) for i in range(5)),
        (6.0,) * 5,
        NOW,
        46.5,
        15.5,
        SETTINGS.timezone,
        SETTINGS.revision,
        request.generation,
    )


class Blocked:
    def __init__(self):
        self.entered = Event()
        self.release = Event()
        self.done = Event()
        self.calls = 0
        self.daemon = False

    def __call__(self, settings, now, generation):
        self.calls += 1
        self.daemon = current_thread().daemon
        self.entered.set()
        self.release.wait(3)
        self.done.set()
        return window(WeatherRequest(settings, now, generation))


def test_stalled_deadline_published_once_and_no_thread_growth() -> None:
    fetch = Blocked()
    clock = [10.0]
    wake = Event()
    worker = WeatherWorker(fetch, wake.set, lambda: clock[0])
    request = WeatherRequest(SETTINGS, NOW, 1)
    try:
        assert worker.submit(request)
        assert fetch.entered.wait(1)
        assert fetch.daemon
        assert worker.poll() is None
        clock[0] = 15.0
        result = worker.poll()
        assert result.request == request
        assert result.window is None and result.error == "deadline_exceeded"
        assert worker.poll() is None
        for generation in range(2, 100):
            assert not worker.submit(WeatherRequest(SETTINGS, NOW, generation))
        assert fetch.calls == 1
        fetch.release.set()
        assert wake.wait(1)
        assert worker.poll() is None
    finally:
        fetch.release.set()
        worker.stop()


@pytest.mark.parametrize("elapsed", [5.0, 6.0])
def test_completed_but_unpolled_result_expires(elapsed) -> None:
    clock = [0.0]
    wake = Event()
    worker = WeatherWorker(
        lambda s, n, g: window(WeatherRequest(s, n, g)), wake.set, lambda: clock[0]
    )
    try:
        assert worker.submit(WeatherRequest(SETTINGS, NOW, 0))
        assert wake.wait(1)
        clock[0] = elapsed
        assert worker.poll().error == "deadline_exceeded"
    finally:
        worker.stop()


def test_success_immutable_and_wake_only_notification() -> None:
    wake = Event()
    worker = WeatherWorker(
        lambda s, n, g: window(WeatherRequest(s, n, g)), wake.set, lambda: 0.0
    )
    try:
        request = WeatherRequest(SETTINGS, NOW, 0)
        assert worker.submit(request)
        assert wake.wait(1)
        assert not worker.submit(request)
        result = worker.poll()
        assert result.window == window(request) and result.error is None
        with pytest.raises(FrozenInstanceError):
            result.error = "changed"
        with pytest.raises(FrozenInstanceError):
            request.generation = 4
        assert worker.poll() is None
    finally:
        worker.stop()


def test_cancel_old_generation_and_bounded_shutdown() -> None:
    fetch = Blocked()
    wake = Event()
    worker = WeatherWorker(fetch, wake.set, lambda: 0.0)
    assert worker.submit(WeatherRequest(SETTINGS, NOW, 0))
    assert fetch.entered.wait(1)
    worker.cancel()
    assert not worker.submit(WeatherRequest(SETTINGS, NOW, 1))
    start = monotonic()
    worker.stop(timeout_s=0.02)
    assert monotonic() - start < 0.5
    assert not worker.submit(WeatherRequest(SETTINGS, NOW, 2))
    fetch.release.set()
    assert wake.wait(1)
    assert worker.poll() is None


def test_exception_details_are_not_published() -> None:
    wake = Event()

    def fail(*_):
        raise RuntimeError("provider-body-or-secret")

    worker = WeatherWorker(fail, wake.set, lambda: 0.0)
    try:
        assert worker.submit(WeatherRequest(SETTINGS, NOW, 0))
        assert wake.wait(1)
        assert worker.poll().error == "fetch_failed"
    finally:
        worker.stop()


def test_transport_completion_after_deadline_cannot_publish_success() -> None:
    clock = [12.0]
    wake = Event()

    def fetch(s, n, g):
        clock[0] = 17.0
        return window(WeatherRequest(s, n, g))

    worker = WeatherWorker(fetch, wake.set, lambda: clock[0])
    try:
        assert worker.submit(WeatherRequest(SETTINGS, NOW, 1))
        assert wake.wait(1)
        result = worker.poll()
        assert result.error == "deadline_exceeded"
        assert result.started_mono == 12.0
        assert result.window is None
    finally:
        worker.stop()


def test_cancel_discards_completed_result_and_older_generation_rejected() -> None:
    wake = Event()
    worker = WeatherWorker(
        lambda s, n, g: window(WeatherRequest(s, n, g)), wake.set, lambda: 10.0
    )
    try:
        assert worker.submit(WeatherRequest(SETTINGS, NOW, 4))
        assert wake.wait(1)
        worker.cancel()
        assert worker.poll() is None
        assert not worker.submit(WeatherRequest(SETTINGS, NOW, 3))
    finally:
        worker.stop()


def test_mismatched_generation_result_is_failed() -> None:
    wake = Event()
    worker = WeatherWorker(
        lambda s, n, g: window(WeatherRequest(s, n, g + 1)), wake.set, lambda: 10.0
    )
    try:
        assert worker.submit(WeatherRequest(SETTINGS, NOW, 1))
        assert wake.wait(1)
        result = worker.poll()
        assert result.error == "provenance_mismatch" and result.window is None
    finally:
        worker.stop()


def test_notification_error_keeps_poll_result_available() -> None:
    notified = Event()

    def wake():
        notified.set()
        raise RuntimeError("notification failed")

    worker = WeatherWorker(
        lambda s, n, g: window(WeatherRequest(s, n, g)), wake, lambda: 10.0
    )
    try:
        assert worker.submit(WeatherRequest(SETTINGS, NOW, 0))
        assert notified.wait(1)
        result = worker.poll()
        assert result.error is None and result.started_mono == 10.0
    finally:
        worker.stop()


def test_shutdown_caps_supplied_timeout_at_one_second() -> None:
    fetch = Blocked()
    worker = WeatherWorker(fetch, lambda: None, lambda: 0.0)
    try:
        assert worker.submit(WeatherRequest(SETTINGS, NOW, 0))
        assert fetch.entered.wait(1)
        start = monotonic()
        worker.stop(100.0)
        assert monotonic() - start < 1.15
        assert worker.poll() is None
    finally:
        fetch.release.set()
        worker.stop()


def test_late_cancelled_reply_is_discarded_before_new_generation() -> None:
    fetch = Blocked()
    wake = Event()
    worker = WeatherWorker(fetch, wake.set, lambda: 10.0)
    try:
        assert worker.submit(WeatherRequest(SETTINGS, NOW, 1))
        assert fetch.entered.wait(1)
        worker.cancel()
        assert not worker.submit(WeatherRequest(SETTINGS, NOW, 2))
        fetch.release.set()
        assert wake.wait(1)
        assert worker.poll() is None
        wake.clear()
        request = WeatherRequest(SETTINGS, NOW, 2)
        limit = monotonic() + 1.0
        while not worker.submit(request):
            assert monotonic() < limit
            Event().wait(0.001)
        assert wake.wait(1)
        result = worker.poll()
        assert result.request.generation == 2
        assert result.window.generation == 2
        assert result.error is None
        assert fetch.calls == 2
    finally:
        fetch.release.set()
        worker.stop()


@pytest.mark.parametrize("elapsed", [-1.0, float("nan"), float("inf")])
def test_broken_monotonic_clock_fails_closed(elapsed) -> None:
    clock = [10.0]
    wake = Event()
    worker = WeatherWorker(
        lambda s, n, g: window(WeatherRequest(s, n, g)), wake.set, lambda: clock[0]
    )
    try:
        assert worker.submit(WeatherRequest(SETTINGS, NOW, 0))
        assert wake.wait(1)
        clock[0] = 10.0 + elapsed
        assert worker.poll().error == "deadline_exceeded"
    finally:
        worker.stop()
