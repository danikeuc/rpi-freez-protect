from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, model_validator

from freeze_protect.adapters.simulation import (
    SimulatedForecastSource,
    SimulatedRelayDriver,
    SimulatedTemperatureSource,
)
from freeze_protect.api.auth import build_admin_guard, require_confirmation
from freeze_protect.application.service import ControlService
from freeze_protect.domain.models import (
    AuditEvent,
    Decision,
    ForecastSnapshot,
    RelayCommand,
    SafetySettings,
    SensorHealth,
    TemperatureReading,
)
from freeze_protect.persistence.sqlite import (
    SettingsVersionConflict,
    SQLiteEventStore,
    SQLiteSettingsStore,
)


class SettingsInput(BaseModel):
    protection_threshold_c: float
    release_threshold_c: float
    release_days: int
    sensor_stale_after_s: int
    minimum_protection_dwell_s: int
    settings_version: int

    def to_domain(self) -> SafetySettings:
        return SafetySettings(**self.model_dump())


class SimulationInput(BaseModel):
    value_c: float | None = None
    health: SensorHealth = SensorHealth.HEALTHY
    daily_minima_c: list[float] | None = None

    @model_validator(mode="after")
    def validate_healthy_value(self) -> SimulationInput:
        if self.health is SensorHealth.HEALTHY and self.value_c is None:
            raise ValueError("value_c is required for a healthy sensor")
        return self


def create_app(
    database_path: Path,
    admin_token: str | None,
    development_mode: bool,
    *,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    clock_fn = clock or _now
    settings_store = SQLiteSettingsStore(database_path)
    event_store = SQLiteEventStore(database_path)
    temperature_source = SimulatedTemperatureSource(
        TemperatureReading(
            value_c=None,
            observed_at=clock_fn(),
            health=SensorHealth.STALE,
        )
    )
    forecast_source = SimulatedForecastSource(None)
    relay_driver = SimulatedRelayDriver()
    service = ControlService(
        temperature_source=temperature_source,
        forecast_source=forecast_source,
        relay_driver=relay_driver,
        event_store=event_store,
        settings=settings_store.load(),
        clock=clock_fn,
    )
    require_admin = build_admin_guard(admin_token)

    app = FastAPI(title="RPi Freeze Protect", version="0.1.0")
    app.state.control_service = service
    app.state.relay_driver = relay_driver

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"service": "ok", "state": service.state.value}

    @app.get("/api/v1/status")
    def get_status() -> dict[str, object]:
        return {
            "state": service.state.value,
            "last_reading": _reading_payload(service.last_reading),
            "last_decision": (
                _decision_payload(service.last_decision)
                if service.last_decision is not None
                else None
            ),
            "settings_version": service.settings.settings_version,
        }

    @app.get("/api/v1/events")
    def get_events(
        _admin: None = Depends(require_admin),
        limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        return {
            "items": [
                {
                    "id": event.id,
                    "occurred_at": event.occurred_at.isoformat(),
                    "event_type": event.event_type,
                    "payload": dict(event.payload),
                }
                for event in event_store.list(limit, offset)
            ],
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/v1/settings")
    def get_settings(
        _admin: None = Depends(require_admin),
    ) -> dict[str, object]:
        return asdict(service.settings)

    @app.put("/api/v1/settings")
    def put_settings(
        payload: SettingsInput,
        _admin: None = Depends(require_admin),
    ) -> dict[str, object]:
        try:
            settings = payload.to_domain()
            saved = settings_store.save(settings)
        except SettingsVersionConflict as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        service.update_settings(saved)
        event_store.append(
            AuditEvent(
                id=str(uuid4()),
                occurred_at=clock_fn(),
                event_type="settings_changed",
                payload={"settings_version": saved.settings_version},
            )
        )
        return asdict(saved)

    @app.post("/api/v1/commands/open")
    def open_command(
        _admin: None = Depends(require_admin),
        x_confirm_command: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        require_confirmation(x_confirm_command, RelayCommand.OPEN.value)
        return _manual_command_response(service, RelayCommand.OPEN)

    @app.post("/api/v1/commands/protect")
    def protect_command(
        _admin: None = Depends(require_admin),
        x_confirm_command: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        require_confirmation(x_confirm_command, RelayCommand.CLOSE_OR_PROTECT.value)
        return _manual_command_response(service, RelayCommand.CLOSE_OR_PROTECT)

    @app.post("/api/v1/commands/stop")
    def stop_command(
        _admin: None = Depends(require_admin),
        x_confirm_command: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        require_confirmation(x_confirm_command, RelayCommand.STOP.value)
        return _manual_command_response(service, RelayCommand.STOP)

    @app.post("/api/v1/commands/clear-fault")
    def clear_fault(
        _admin: None = Depends(require_admin),
        x_confirm_command: Annotated[str | None, Header()] = None,
    ) -> dict[str, str]:
        require_confirmation(x_confirm_command, "CLEAR_FAULT")
        decision = service.clear_fault()
        if decision.state.value == "FAULT":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=decision.reason)
        return _decision_payload(decision)

    if development_mode:

        @app.post("/api/v1/simulation/temperature")
        def simulate_temperature(
            payload: SimulationInput,
            _admin: None = Depends(require_admin),
        ) -> dict[str, str]:
            temperature_source.set(
                TemperatureReading(
                    value_c=payload.value_c,
                    observed_at=clock_fn(),
                    health=payload.health,
                )
            )
            if payload.daily_minima_c is not None:
                forecast_source.set(
                    ForecastSnapshot(tuple(payload.daily_minima_c), clock_fn())
                )
            return _decision_payload(service.run_cycle())

    return app


def _manual_command_response(
    service: ControlService,
    command: RelayCommand,
) -> dict[str, str]:
    decision = service.manual_command(command)
    if command is not RelayCommand.STOP and decision.command is RelayCommand.STOP:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=decision.reason)
    return _decision_payload(decision)


def _now() -> datetime:
    return datetime.now(UTC)


def _decision_payload(decision: Decision) -> dict[str, str]:
    return {
        "state": decision.state.value,
        "command": decision.command.value,
        "reason": decision.reason,
    }


def _reading_payload(
    reading: TemperatureReading | None,
) -> dict[str, object] | None:
    if reading is None:
        return None
    return {
        "value_c": reading.value_c,
        "observed_at": reading.observed_at.isoformat(),
        "health": reading.health.value,
    }
