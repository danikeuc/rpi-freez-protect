from threading import Event

from freeze_protect.application.service import PeriodicControlLoop


class CountingService:
    def __init__(self) -> None:
        self.first_cycle = Event()
        self.second_cycle = Event()
        self.cycles = 0

    def refresh_forecast(self) -> None:
        return None

    def run_cycle(self) -> None:
        self.cycles += 1
        if self.cycles == 1:
            self.first_cycle.set()
        if self.cycles == 2:
            self.second_cycle.set()

    def seconds_until_timed_shower_expiry(self) -> float | None:
        return None

    def handle_persistence_failure(self) -> None:
        raise AssertionError("the loop should not fault in this test")


def test_wake_interrupts_a_normal_cycle_wait_for_a_new_timed_shower() -> None:
    service = CountingService()
    loop = PeriodicControlLoop(
        service,  # type: ignore[arg-type]
        cycle_interval_s=10.0,
        forecast_interval_s=100.0,
    )
    loop.start()
    try:
        assert service.first_cycle.wait(timeout=1.0)
        loop.wake()
        assert service.second_cycle.wait(timeout=1.0)
    finally:
        loop.stop()
