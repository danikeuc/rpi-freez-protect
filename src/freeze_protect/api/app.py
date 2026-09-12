from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, NoReturn, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from freeze_protect.adapters.ds18b20 import Ds18b20TemperatureSource
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
    require_confirmation,
)
from freeze_protect.application.ports import ActuatorDriver, AdapterError
from freeze_protect.application.service import (
    ControlService,
    ControlStatus,
    PeriodicControlLoop,
)
from freeze_protect.domain.models import (
    ActuatorCommand,
    AuditEvent,
    ControllerState,
    Decision,
    ForecastSnapshot,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)
from freeze_protect.persistence.sqlite import (
    SettingsVersionConflict,
    SQLiteEventStore,
    SQLiteForecastStore,
    SQLiteSettingsStore,
)


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
    def command(self, command: ActuatorCommand) -> NoReturn:
        raise AdapterError(f"actuator bridge is not configured for {command.value}")


def create_app(
    database_path: Path,
    admin_token: str | None,
    display_token: str | None,
    development_mode: bool,
    *,
    node_red_url: str | None = None,
    node_red_token: str | None = None,
    clock: Callable[[], datetime] | None = None,
    run_background: bool = True,
) -> FastAPI:
    clock_fn = clock or _now
    settings_store = SQLiteSettingsStore(database_path)
    event_store = SQLiteEventStore(database_path)
    settings = settings_store.load()
    if development_mode:
        temperature_source = SimulatedTemperatureSource(
            TemperatureReading(None, clock_fn(), SensorHealth.CALIBRATION_REQUIRED)
        )
        forecast_store = SimulatedForecastStore()
        forecast_client = SimulatedForecastClient()
        actuator_driver: ActuatorDriver = SimulatedActuatorDriver()
    else:
        temperature_source = Ds18b20TemperatureSource(
            settings_provider=settings_store.load,
            clock=clock_fn,
        )
        forecast_store = SQLiteForecastStore(database_path)
        forecast_client = OpenMeteoForecastClient()
        actuator_driver = _production_actuator(node_red_url, node_red_token)

    service = ControlService(
        temperature_source=temperature_source,
        forecast_store=forecast_store,
        forecast_client=forecast_client,
        actuator_driver=actuator_driver,
        event_store=event_store,
        settings=settings,
        clock=clock_fn,
    )
    control_loop = PeriodicControlLoop(service)
    require_admin = build_admin_guard(admin_token)
    require_display = build_display_guard(display_token)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        service.startup()
        if run_background:
            control_loop.start()
        try:
            yield
        finally:
            control_loop.stop()
            service.drain("shutdown_drain")

    app = FastAPI(title="RPi Freeze Protect", version="0.2.0", lifespan=lifespan)
    app.state.control_service = service
    app.state.relay_driver = actuator_driver
    app.state.temperature_source = temperature_source

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"service": "ok", "state": service.status().state.value}

    @app.get("/api/v1/status")
    def get_status(_admin: None = Depends(require_admin)) -> dict[str, object]:
        return _admin_status_payload(service.status(), service.settings)

    @app.get("/api/v1/events")
    def get_events(
        _admin: None = Depends(require_admin),
        limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        return {
            "items": [_event_payload(event) for event in event_store.list(limit, offset)],
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
        return _display_status_payload(service.status(), service.settings)

    @app.post("/api/v1/display/actions/timed-shower")
    def display_timed_shower(
        _display: None = Depends(require_display),
    ) -> dict[str, object]:
        decision = service.start_timed_shower()
        control_loop.wake()
        return _decision_or_conflict(decision)

    @app.post("/api/v1/display/actions/drain")
    def display_drain(
        _display: None = Depends(require_display),
    ) -> dict[str, object]:
        decision = service.drain("display_drain_requested")
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


def _production_actuator(
    node_red_url: str | None, node_red_token: str | None
) -> ActuatorDriver:
    if not node_red_url or not node_red_token:
        return _UnavailableActuatorDriver()
    return NodeRedActuatorDriver(node_red_url, node_red_token)


def _decision_or_conflict(decision: Decision) -> dict[str, object]:
    typed = cast(Decision, decision)
    if typed.state is ControllerState.FAULT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=typed.reason)
    return {
        "state": typed.state.value,
        "command": typed.command.value,
        "reason": typed.reason,
    }


def _admin_status_payload(
    control: ControlStatus, settings: SafetySettings
) -> dict[str, object]:
    return {
        "state": control.state.value,
        "reason": control.reason,
        "last_reading": _reading_payload(control.last_reading),
        "forecast": _forecast_payload(control.forecast, settings),
        "timed_shower_deadline": _iso(control.timed_shower_deadline),
        "bridge_flow_revision": (
            control.last_receipt.flow_revision if control.last_receipt is not None else None
        ),
        "settings_version": settings.settings_version,
    }


def _display_status_payload(
    control: ControlStatus, settings: SafetySettings
) -> dict[str, object]:
    forecast = _forecast_payload(control.forecast, settings)
    return {
        "state": control.state.value,
        "reason": control.reason,
        "pipe_temperature_c": (
            control.last_reading.value_c if control.last_reading is not None else None
        ),
        "sensor_health": (
            control.last_reading.health.value if control.last_reading is not None else None
        ),
        "forecast": forecast,
        "timed_shower_deadline": _iso(control.timed_shower_deadline),
        "action": (
            "CLOSE_NOW"
            if control.state is ControllerState.TIMED_SHOWER
            else "TIMED_SHOWER"
        ),
        "action_enabled": control.state is not ControllerState.FAULT,
    }


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
