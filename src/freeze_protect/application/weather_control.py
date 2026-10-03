"""Process-local weather coordination. The service lock owns every call here."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

from freeze_protect.application.ports import WeatherWorkerPort
from freeze_protect.application.weather_worker import WeatherRequest
from freeze_protect.domain.weather import (
    WEATHER_REFRESH_SECONDS,
    WeatherEligibility,
    WeatherObservation,
    WeatherSettings,
    evaluate_weather,
)
from freeze_protect.persistence.weather import (
    SQLiteWeatherStore,
    WeatherRevisionConflict,
)


class WeatherCoordinator:
    """Poll only; transport and worker lifetime belong to the application lifespan.

    This object has no actuator authority and no independent lock. ControlService
    serializes settings, polling and snapshots with the same control lock.
    """

    def __init__(
        self,
        store: SQLiteWeatherStore,
        worker: WeatherWorkerPort,
        clock: Callable[[], datetime],
        monotonic_clock: Callable[[], float],
    ) -> None:
        self.store = store
        self._worker = worker
        self._clock = clock
        self._monotonic_clock = monotonic_clock
        self._settings: WeatherSettings | None = None
        self._generation = 0
        self._observation: WeatherObservation | None = None
        self._next_refresh = 0.0
        self._local_date: date | None = None
        self._invalid_reason = "weather_missing"

    @property
    def observation(self) -> WeatherObservation | None:
        return self._observation

    def invalidate(self, reason: str) -> None:
        self._generation += 1
        self._worker.cancel()
        self._observation = None
        self._next_refresh = 0.0
        self._invalid_reason = reason

    def eligibility(self, settings: WeatherSettings) -> WeatherEligibility:
        result = evaluate_weather(
            settings, self._observation, self._clock(), self._monotonic_clock()
        )
        if result.reason == "time_basis_invalid" and self._observation is not None:
            self.invalidate("time_basis_invalid")
        if result.reason == "weather_missing":
            return WeatherEligibility(False, self._invalid_reason)
        return result

    def tick(self) -> WeatherEligibility:
        settings = self.store.load().settings
        now, now_mono = self._clock(), self._monotonic_clock()
        local_date = now.astimezone(ZoneInfo(settings.timezone)).date()
        if settings != self._settings:
            self.invalidate("settings_changed")
            self._settings = settings
        elif self._local_date is not None and local_date != self._local_date:
            self.invalidate("coverage_invalid")
        self._local_date = local_date
        result = self._worker.poll()
        if (
            result is not None
            and result.request.generation == self._generation
            and result.request.settings == settings
        ):
            success = result.error is None and result.window is not None
            previous = self._observation
            # Retain last-success metadata for display, never its authority after
            # a failed latest attempt. A settings/date invalidation discards it.
            self._observation = WeatherObservation(
                result.window if success else previous.window if previous else None,
                result.started_mono
                if success or previous is None
                else previous.received_mono,
                success,
                result.error or "success",
            )
            self._invalid_reason = result.error or "weather_missing"
        eligibility = self.eligibility(settings)
        if (
            settings.enabled
            and settings.latitude is not None
            and settings.longitude is not None
            and now_mono >= self._next_refresh
        ):
            request = WeatherRequest(settings, self._clock(), self._generation)
            if self._worker.submit(request):
                self._next_refresh = now_mono + WEATHER_REFRESH_SECONDS
        return eligibility

    def update_settings(
        self, expected_revision: int, settings: WeatherSettings
    ) -> WeatherSettings:
        record = self.store.load()
        if (
            type(expected_revision) is not int
            or record.settings.revision != expected_revision
        ):
            raise WeatherRevisionConflict("weather settings revision conflict")
        if settings.revision != expected_revision:
            raise WeatherRevisionConflict("weather settings revision conflict")
        saved = self.store.compare_and_swap(
            record.control_revision, replace(record, settings=settings)
        )
        if saved.settings != self._settings:
            self.invalidate("settings_changed")
            self._settings = saved.settings
            self._local_date = None
        return saved.settings
