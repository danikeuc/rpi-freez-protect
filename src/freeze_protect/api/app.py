from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Annotated, NoReturn, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from freeze_protect.adapters.max31865 import Max31865TemperatureSource
from freeze_protect.adapters.node_red import NodeRedActuatorDriver
from freeze_protect.adapters.simulation import (
    InMemoryEventStore,
    SimulatedActuatorDriver,
    SimulatedForecastClient,
    SimulatedForecastStore,
    SimulatedTemperatureSource,
)
from freeze_protect.adapters.weather import OpenMeteoForecastClient
from freeze_protect.api.auth import (
    build_admin_guard,
    build_display_guard,
    build_weather_guard,
    require_confirmation,
)
from freeze_protect.api.weather import (
    action_input,
    read_weather_json,
    settings_input,
    settings_payload,
)
from freeze_protect.application.ports import (
    ActuatorDriver,
    AdapterError,
    EventStore,
    ForecastClient,
    ForecastStore,
    TemperatureSource,
)
from freeze_protect.application.service import (
    ControlService,
    ControlStatus,
    PeriodicControlLoop,
)
from freeze_protect.application.temperature_telemetry import (
    DISPLAY_TEMPERATURE_STALE_AFTER_S,
    TemperatureTelemetrySampler,
)
from freeze_protect.application.weather_actions import (
    WeatherActionError,
    WeatherActionGate,
)
from freeze_protect.application.weather_control import WeatherCoordinator
from freeze_protect.application.weather_worker import WeatherWorker
from freeze_protect.domain.models import (
    ActuatorCommand,
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
from freeze_protect.domain.weather import WeatherSettings, WeatherWindow
from freeze_protect.persistence.sqlite import (
    SettingsVersionConflict,
    SQLiteEventStore,
    SQLiteForecastStore,
    SQLiteSettingsStore,
)
from freeze_protect.persistence.weather import (
    SQLiteWeatherStore,
    WeatherRevisionConflict,
    WeatherStateError,
)

_PRODUCTION_SENSOR_SOURCE_ID = "MAX31865_PT100_SPI0_CE0"


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protection_threshold_c: float
    release_threshold_c: float
    forecast_threshold_c: float
    forecast_days: int
    sensor_stale_after_s: int
    forecast_stale_after_s: int
    timed_shower_default_s: int
    timed_shower_max_s: int
    latitude: float | None
    longitude: float | None
    timezone: str
    sensor_device_id: str | None
    sensor_commissioned: bool
    settings_version: int

    def to_domain(self) -> SafetySettings:
        return SafetySettings(**self.model_dump())


class SimulationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value_c: float | None = None
    health: SensorHealth = SensorHealth.HEALTHY


class _UnavailableActuatorDriver:
    def command(
        self, command: ActuatorCommand, *, supply_action: SupplyAction | None = None
    ) -> NoReturn:
        raise AdapterError(f"actuator bridge is not configured for {command.value}")


def create_app(
    database_path: Path,
    admin_token: str | None,
    display_token: str | None,
    development_mode: bool,
    *,
    weather_settings_token: str | None = None,
    control_mode: ControlMode = ControlMode.SAFE_DRAIN,
    node_red_url: str | None = None,
    node_red_token: str | None = None,
    clock: Callable[[], datetime] | None = None,
    run_background: bool = True,
    monotonic_clock: Callable[[], float] = monotonic,
) -> FastAPI:
    clock_fn = clock or _now
    weather_store: SQLiteWeatherStore | None = None
    assembly_failed = False
    try:
        # Weather identity must be checked before legacy constructors can create
        # an absent database and hide loss of established durable state.
        weather_store = SQLiteWeatherStore(database_path)
    except WeatherStateError:
        assembly_failed = True
    settings_store: SQLiteSettingsStore | None = None
    event_store: EventStore
    if weather_store is None:
        settings = SafetySettings()
        event_store = InMemoryEventStore()
    else:
        settings_store = SQLiteSettingsStore(database_path)
        event_store = SQLiteEventStore(database_path)
        settings = settings_store.load()
    temperature_source: TemperatureSource
    forecast_store: ForecastStore
    forecast_client: ForecastClient
    if development_mode:
        temperature_source = SimulatedTemperatureSource(
            TemperatureReading(None, clock_fn(), SensorHealth.CALIBRATION_REQUIRED)
        )
        forecast_store = SimulatedForecastStore()
        forecast_client = SimulatedForecastClient()
        actuator_driver: ActuatorDriver = SimulatedActuatorDriver()
    else:
        if settings_store is not None:
            settings = settings_store.bind_sensor_source(_PRODUCTION_SENSOR_SOURCE_ID)
        temperature_source = Max31865TemperatureSource(clock=clock_fn)
        forecast_store = (
            SQLiteForecastStore(database_path)
            if weather_store is not None
            else SimulatedForecastStore()
        )
        forecast_client = OpenMeteoForecastClient()
        actuator_driver = _production_actuator(node_red_url, node_red_token)

    weather_worker: WeatherWorker | None = None
    weather_coordinator: WeatherCoordinator | None = None
    if weather_store is not None:

        def development_weather(
            _settings: WeatherSettings, _now: datetime, _generation: int
        ) -> WeatherWindow:
            raise AdapterError("simulated weather unavailable")

        weather_fetch = (
            development_weather
            if development_mode
            else OpenMeteoForecastClient().fetch_window
        )
        # Constructors never submit; this wake-only closure is bound before startup.
        weather_worker = WeatherWorker(
            weather_fetch, lambda: control_loop.wake(), monotonic_clock
        )
        weather_coordinator = WeatherCoordinator(
            weather_store, weather_worker, clock_fn, monotonic_clock
        )

    service = ControlService(
        temperature_source=temperature_source,
        forecast_store=forecast_store,
        forecast_client=forecast_client,
        actuator_driver=actuator_driver,
        event_store=event_store,
        settings=settings,
        clock=clock_fn,
        mode=control_mode,
        monotonic_clock=monotonic_clock,
        weather_coordinator=weather_coordinator,
        weather_store=weather_store,
    )
    temperature_telemetry_sampler = (
        TemperatureTelemetrySampler(temperature_source, clock=clock_fn)
        if control_mode is not ControlMode.AUTOMATIC
        else None
    )
    control_loop = PeriodicControlLoop(service)
    require_admin = build_admin_guard(admin_token)
    require_display = build_display_guard(display_token)
    # A reused credential cannot grant an additional scope.
    scoped_weather_token = (
        weather_settings_token
        if weather_settings_token not in (admin_token, display_token)
        else None
    )
    require_weather = build_weather_guard(scoped_weather_token)

    def display_payload(read_only: bool = False) -> dict[str, object]:
        # Weather status expires timers first, so the whole response is coherent.
        weather = (
            service.weather_status(expire_timer=not read_only)
            if weather_store is not None
            else None
        )
        control = service.status(expire_timer=not read_only)
        temperature = (
            control.last_reading
            if control.mode is ControlMode.AUTOMATIC
            else temperature_telemetry_sampler.snapshot()
            if temperature_telemetry_sampler is not None
            else None
        )
        payload = _display_status_payload(
            control,
            service.settings,
            _normalize_display_temperature(temperature, clock_fn()),
        )
        observation = weather.observation if weather is not None else None
        window = observation.window if observation is not None else None
        payload.update(
            {
                "weather_assistance_version": 1,
                "operation": weather.operation if weather is not None else "FAULT",
                "control_revision": weather.record.control_revision
                if weather is not None
                else None,
                "action_nonce": None,
                "weather": {
                    "enabled": weather.record.settings.enabled
                    if weather is not None
                    else False,
                    "available": bool(
                        observation is not None
                        and observation.latest_attempt_ok
                        and window is not None
                    ),
                    "eligible": weather.eligibility.eligible
                    if weather is not None
                    else False,
                    "reason": weather.eligibility.reason
                    if weather is not None
                    else "storage_unavailable",
                    "dates": [day.isoformat() for day in window.dates]
                    if window is not None
                    else [],
                    "minima_c": list(window.minima_c) if window is not None else [],
                    "weather_codes": list(window.weather_codes)
                    if window is not None
                    else [],
                    "last_successful_check": _iso(window.fetched_at)
                    if window is not None
                    else None,
                },
            }
        )
        if control.mode is ControlMode.WEATHER_ASSISTED:
            payload["timed_shower_duration_supported"] = True
        return payload

    action_gate: WeatherActionGate | None = None
    if weather_store is not None:
        try:
            action_gate = WeatherActionGate(
                service, weather_store, display_payload, monotonic_clock
            )
        except WeatherStateError:
            assembly_failed = True

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            service.startup()
            if assembly_failed:
                service.handle_persistence_failure()
            if action_gate is not None:
                try:
                    action_gate.recover_pending()
                except WeatherStateError:
                    service.handle_persistence_failure()
            if run_background:
                if temperature_telemetry_sampler is not None:
                    temperature_telemetry_sampler.start()
                control_loop.start()
            yield
        finally:
            try:
                if temperature_telemetry_sampler is not None:
                    temperature_telemetry_sampler.stop()
            finally:
                try:
                    control_loop.stop()
                finally:
                    try:
                        service.shutdown()
                        if action_gate is not None:
                            action_gate.promote_completed()
                    finally:
                        if weather_worker is not None:
                            weather_worker.stop()

    app = FastAPI(title="RPi Freeze Protect", version="1.2.0", lifespan=lifespan)
    app.state.control_service = service
    app.state.relay_driver = actuator_driver
    app.state.temperature_source = temperature_source
    app.state.temperature_telemetry_sampler = temperature_telemetry_sampler
    app.state.weather_store = weather_store
    app.state.weather_worker = weather_worker
    app.state.weather_action_gate = action_gate

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"service": "ok", "state": service.status().state.value}

    @app.get("/api/v1/status")
    def get_status(_admin: None = Depends(require_admin)) -> dict[str, object]:
        return _admin_status_payload(
            service.status(), service.settings, _sensor_diagnostics(temperature_source)
        )

    @app.get("/api/v1/events")
    def get_events(
        _admin: None = Depends(require_admin),
        limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        if not isinstance(event_store, SQLiteEventStore):
            raise HTTPException(503, "event storage unavailable")
        return {
            "items": [
                _event_payload(event) for event in event_store.list(limit, offset)
            ],
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/v1/settings")
    def get_settings(_admin: None = Depends(require_admin)) -> dict[str, object]:
        return asdict(service.settings)

    @app.put("/api/v1/settings")
    def put_settings(
        payload: SettingsInput,
        _admin: None = Depends(require_admin),
    ) -> dict[str, object]:
        try:
            if settings_store is None:
                raise WeatherStateError("settings storage unavailable")
            saved = settings_store.save(payload.to_domain())
        except SettingsVersionConflict as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(error)
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
            ) from error
        except Exception as error:
            service.handle_persistence_failure()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="settings persistence failed; valves were returned to DRAIN",
            ) from error
        decision = service.update_settings(saved)
        if decision.state is ControllerState.FAULT:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=decision.reason,
            )
        return asdict(saved)

    @app.post("/api/v1/commands/clear-fault")
    def clear_fault(
        _admin: None = Depends(require_admin),
        x_confirm_command: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_confirmation(x_confirm_command, "CLEAR_FAULT")
        return _decision_or_conflict(service.clear_fault())

    @app.get("/api/v1/display/status")
    def display_status(
        _display: None = Depends(require_display),
    ) -> dict[str, object]:
        if action_gate is not None:
            try:
                return action_gate.status()
            except (WeatherStateError, WeatherRevisionConflict):
                service.handle_persistence_failure()
        control = service.status()
        payload = _display_status_payload(control, service.settings, None)
        payload.update(
            {
                "weather_assistance_version": 1,
                "operation": "FAULT",
                "control_revision": None,
                "action_nonce": None,
                "weather": {
                    "enabled": False,
                    "available": False,
                    "eligible": False,
                    "reason": "storage_unavailable",
                    "dates": [],
                    "minima_c": [],
                    "weather_codes": [],
                    "last_successful_check": None,
                },
            }
        )
        return payload

    @app.get("/api/v1/display/weather-settings")
    def get_weather_settings(
        _weather: None = Depends(require_weather),
    ) -> dict[str, object]:
        try:
            with service.weather_action_guard() as record:
                return settings_payload(record.settings)
        except WeatherStateError as error:
            raise HTTPException(503, "weather settings unavailable") from error

    @app.put("/api/v1/display/weather-settings")
    async def put_weather_settings(
        request: Request, _weather: None = Depends(require_weather)
    ) -> dict[str, object]:
        payload = await read_weather_json(
            request,
            {"expected_revision", "enabled", "latitude", "longitude", "timezone"},
        )
        settings = settings_input(payload)
        try:
            saved = await run_in_threadpool(
                service.update_weather_settings, settings.revision, settings
            )
            control_loop.wake()
            return settings_payload(saved)
        except WeatherRevisionConflict as error:
            raise HTTPException(409, "weather settings revision conflict") from error
        except WeatherStateError as error:
            raise HTTPException(503, "weather settings unavailable") from error

    async def weather_action(request: Request, action: str) -> dict[str, object]:
        keys = {"request_id", "expected_control_revision", "action_nonce"}
        if action == "start":
            keys.add("duration_seconds")
        payload = action_input(await read_weather_json(request, keys))
        if action_gate is None:
            raise HTTPException(503, "weather controller unavailable")
        try:
            result = await run_in_threadpool(action_gate.execute, action, payload)
            control_loop.wake()
            return asdict(result)
        except WeatherActionError as error:
            raise HTTPException(error.status_code, error.detail) from error
        except WeatherRevisionConflict as error:
            raise HTTPException(409, "weather controller not ready") from error
        except WeatherStateError as error:
            raise HTTPException(503, "weather controller unavailable") from error

    @app.post("/api/v1/display/actions/start")
    async def display_start(
        request: Request, _display: None = Depends(require_display)
    ) -> dict[str, object]:
        return await weather_action(request, "start")

    @app.post("/api/v1/display/actions/stop")
    async def display_stop(
        request: Request, _display: None = Depends(require_display)
    ) -> dict[str, object]:
        return await weather_action(request, "stop")

    @app.post("/api/v1/display/actions/timed-shower")
    async def display_timed_shower(
        request: Request,
        _display: None = Depends(require_display),
    ) -> dict[str, object]:
        duration_seconds = await _display_duration(request)
        decision = await run_in_threadpool(service.start_timed_shower, duration_seconds)
        if (
            duration_seconds is not None
            and decision.reason == "manual_duration_requires_manual_mode"
        ) or decision.command is not ActuatorCommand.SUPPLY:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=decision.reason
            )
        control_loop.wake()
        return _decision_or_conflict(decision)

    @app.post("/api/v1/display/actions/drain")
    async def display_drain(
        request: Request,
        _display: None = Depends(require_display),
    ) -> dict[str, object]:
        await _require_empty_display_body(request)
        decision = await run_in_threadpool(service.drain, "display_drain_requested")
        control_loop.wake()
        return _decision_or_conflict(decision)

    if development_mode:
        simulated_temperature = cast(SimulatedTemperatureSource, temperature_source)

        @app.post("/api/v1/simulation/temperature")
        def simulate_temperature(
            payload: SimulationInput,
            _admin: None = Depends(require_admin),
        ) -> dict[str, object]:
            simulated_temperature.set(
                TemperatureReading(
                    payload.value_c,
                    clock_fn(),
                    payload.health,
                )
            )
            return _decision_or_conflict(service.run_cycle())

    return app


async def _require_empty_display_body(request: Request) -> None:
    if await request.body():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="display actions do not accept a request body",
        )


async def _display_duration(request: Request) -> int | None:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 256:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="display action body exceeds 256 bytes",
            )
        body.extend(chunk)
    if not body:
        return None

    def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject_constant(_value: str) -> NoReturn:
        raise ValueError("invalid JSON constant")

    try:
        payload = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=unique_keys,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid duration body"
        ) from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"duration_seconds"}
        or type(payload["duration_seconds"]) is not int
        or not 60 <= payload["duration_seconds"] <= 600
        or payload["duration_seconds"] % 60 != 0
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid duration body"
        )
    return payload["duration_seconds"]


def _production_actuator(
    node_red_url: str | None, node_red_token: str | None
) -> ActuatorDriver:
    if not node_red_url or not node_red_token:
        return _UnavailableActuatorDriver()
    return NodeRedActuatorDriver(node_red_url, node_red_token)


def _decision_or_conflict(decision: Decision) -> dict[str, object]:
    if decision.state is ControllerState.FAULT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=decision.reason
        )
    return {
        "state": decision.state.value,
        "command": decision.command.value,
        "reason": decision.reason,
    }


def _admin_status_payload(
    control: ControlStatus,
    settings: SafetySettings,
    sensor_diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "mode": control.mode.value,
        "state": control.state.value,
        "reason": control.reason,
        "last_reading": _reading_payload(control.last_reading),
        "sensor_diagnostics": sensor_diagnostics,
        "forecast": _forecast_payload(control.forecast, settings),
        "timed_shower_deadline": _iso(control.timed_shower_deadline),
        "bridge_flow_revision": (
            control.last_receipt.flow_revision
            if control.last_receipt is not None
            else None
        ),
        "settings_version": settings.settings_version,
    }


def _normalize_display_temperature(
    reading: TemperatureReading | None, now: datetime
) -> TemperatureReading | None:
    if reading is None:
        return None
    age_s = (now - reading.observed_at).total_seconds()
    if reading.health is SensorHealth.HEALTHY and (
        age_s < 0 or age_s >= DISPLAY_TEMPERATURE_STALE_AFTER_S
    ):
        return TemperatureReading(None, reading.observed_at, SensorHealth.STALE)
    if reading.health is not SensorHealth.HEALTHY:
        return TemperatureReading(None, reading.observed_at, reading.health)
    return reading


def _display_status_payload(
    control: ControlStatus,
    settings: SafetySettings,
    temperature: TemperatureReading | None,
) -> dict[str, object]:
    forecast = _forecast_payload(control.forecast, settings)
    return {
        "mode": control.mode.value,
        "command": control.command.value,
        "remaining_seconds": control.remaining_seconds,
        "state": control.state.value,
        "reason": control.reason,
        "forecast": forecast,
        "timed_shower_deadline": _iso(control.timed_shower_deadline),
        "timed_shower_duration_supported": control.mode is ControlMode.MANUAL_TIMED,
        "action": (
            "CLOSE_NOW"
            if control.state is ControllerState.TIMED_SHOWER
            else "TIMED_SHOWER"
        ),
        "action_enabled": control.state is not ControllerState.FAULT
        and control.mode is not ControlMode.SAFE_DRAIN,
        "pipe_temperature_c": temperature.value_c if temperature is not None else None,
        "sensor_health": (
            temperature.health.value
            if temperature is not None
            else SensorHealth.STALE.value
        ),
    }


def _sensor_diagnostics(source: TemperatureSource) -> dict[str, object] | None:
    if isinstance(source, Max31865TemperatureSource):
        return source.diagnostics()
    return None


def _reading_payload(reading: TemperatureReading | None) -> dict[str, object] | None:
    if reading is None:
        return None
    return {
        "value_c": reading.value_c,
        "observed_at": reading.observed_at.isoformat(),
        "health": reading.health.value,
    }


def _forecast_payload(
    forecast: ForecastSnapshot | None, settings: SafetySettings
) -> dict[str, object]:
    if forecast is None:
        return {"available": False, "fresh": False, "dates": [], "minima_c": []}
    return {
        "available": True,
        "fresh": forecast.is_fresh(_now(), settings.forecast_stale_after_s),
        "dates": [value.isoformat() for value in forecast.dates],
        "minima_c": list(forecast.daily_minima_c),
        "fetched_at": forecast.fetched_at.isoformat(),
    }


def _event_payload(event: AuditEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at.isoformat(),
        "event_type": event.event_type,
        "payload": dict(event.payload),
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _now() -> datetime:
    return datetime.now(UTC)
