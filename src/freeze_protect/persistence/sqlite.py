from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path
from typing import cast

from freeze_protect.domain.models import AuditEvent, ForecastSnapshot, SafetySettings

_ACTIVE_SENSOR_SOURCE_KEY = "sensor_source_id"
_COMMISSIONED_SENSOR_SOURCE_KEY = "commissioned_sensor_source_id"
_COMMISSIONED_SETTINGS_VERSION_KEY = "commissioned_settings_version"


class SettingsVersionConflict(ValueError):
    """Raised when a settings update skips or repeats a configuration version."""


class SQLiteSettingsStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        _initialize(database_path)

    def load(self) -> SafetySettings:
        with _connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM settings WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return SafetySettings()
        return _load_settings(row["payload_json"])

    def save(self, settings: SafetySettings) -> SafetySettings:
        with _connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT version FROM settings WHERE singleton = 1"
            ).fetchone()
            if row is not None and settings.settings_version != row["version"] + 1:
                raise SettingsVersionConflict(
                    "settings_version must be exactly one greater than the stored version"
                )
            _write_settings(connection, settings)
            if settings.sensor_commissioned:
                source_id = _metadata_value(connection, _ACTIVE_SENSOR_SOURCE_KEY)
                if source_id is not None:
                    _write_metadata(
                        connection, _COMMISSIONED_SENSOR_SOURCE_KEY, source_id
                    )
                    _write_metadata(
                        connection,
                        _COMMISSIONED_SETTINGS_VERSION_KEY,
                        str(settings.settings_version),
                    )
            else:
                _clear_commissioning_approval(connection)
        return settings

    def bind_sensor_source(self, source_id: str) -> SafetySettings:
        if not source_id:
            raise ValueError("source_id must be non-empty")
        with _connect(self._database_path) as connection:
            active_source_id = _metadata_value(connection, _ACTIVE_SENSOR_SOURCE_KEY)
            commissioned_source_id = _metadata_value(
                connection, _COMMISSIONED_SENSOR_SOURCE_KEY
            )
            commissioned_version = _metadata_value(
                connection, _COMMISSIONED_SETTINGS_VERSION_KEY
            )
            settings_row = connection.execute(
                "SELECT payload_json FROM settings WHERE singleton = 1"
            ).fetchone()
            settings = (
                SafetySettings()
                if settings_row is None
                else _load_settings(settings_row["payload_json"])
            )
            approval_matches = (
                settings.sensor_commissioned
                and commissioned_source_id == source_id
                and commissioned_version == str(settings.settings_version)
            )
            if active_source_id == source_id and (
                not settings.sensor_commissioned or approval_matches
            ):
                if not settings.sensor_commissioned:
                    _clear_commissioning_approval(connection)
                return settings
            if settings.sensor_commissioned:
                settings = replace(
                    settings,
                    sensor_commissioned=False,
                    settings_version=settings.settings_version + 1,
                )
                _write_settings(connection, settings)
            _clear_commissioning_approval(connection)
            _write_metadata(connection, _ACTIVE_SENSOR_SOURCE_KEY, source_id)
        return settings


class SQLiteForecastStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        _initialize(database_path)

    def load(self) -> ForecastSnapshot | None:
        with _connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM forecast_cache WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return None
        return _load_forecast(row["payload_json"])

    def save(self, snapshot: ForecastSnapshot) -> None:
        payload = {
            "dates": [value.isoformat() for value in snapshot.dates],
            "daily_minima_c": list(snapshot.daily_minima_c),
            "source_generated_at": (
                snapshot.source_generated_at.isoformat()
                if snapshot.source_generated_at is not None
                else None
            ),
            "fetched_at": snapshot.fetched_at.isoformat(),
            "latitude": snapshot.latitude,
            "longitude": snapshot.longitude,
        }
        with _connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO forecast_cache (singleton, payload_json, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                  payload_json = excluded.payload_json,
                  updated_at = excluded.updated_at
                """,
                (
                    json.dumps(payload, sort_keys=True),
                    datetime.now().astimezone().isoformat(),
                ),
            )


class SQLiteEventStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        _initialize(database_path)

    def append(self, event: AuditEvent) -> None:
        with _connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO audit_events (id, occurred_at, event_type, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.occurred_at.isoformat(),
                    event.event_type,
                    json.dumps(event.payload, sort_keys=True),
                ),
            )

    def list(self, limit: int, offset: int) -> list[AuditEvent]:
        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        if offset < 0:
            raise ValueError("offset must not be negative")

        with _connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, occurred_at, event_type, payload_json
                FROM audit_events
                ORDER BY occurred_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [
            AuditEvent(
                id=row["id"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                event_type=row["event_type"],
                payload=_load_object(row["payload_json"]),
            )
            for row in rows
        ]


def _connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _initialize(database_path: Path) -> None:
    with _connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
              version INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS forecast_cache (
              singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
              payload_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
              id TEXT PRIMARY KEY,
              occurred_at TEXT NOT NULL,
              event_type TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_events_occurred_at
              ON audit_events (occurred_at DESC, id DESC);
            CREATE TABLE IF NOT EXISTS runtime_metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )


def _write_settings(
    connection: sqlite3.Connection, settings: SafetySettings
) -> None:
    connection.execute(
        """
        INSERT INTO settings (singleton, version, payload_json, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(singleton) DO UPDATE SET
          version = excluded.version,
          payload_json = excluded.payload_json,
          updated_at = excluded.updated_at
        """,
        (
            settings.settings_version,
            json.dumps(asdict(settings), sort_keys=True),
            datetime.now().astimezone().isoformat(),
        ),
    )


def _metadata_value(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute(
        "SELECT value FROM runtime_metadata WHERE key = ?", (key,)
    ).fetchone()
    return None if row is None else cast(str, row["value"])


def _write_metadata(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO runtime_metadata (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _clear_commissioning_approval(connection: sqlite3.Connection) -> None:
    connection.execute(
        "DELETE FROM runtime_metadata WHERE key IN (?, ?)",
        (_COMMISSIONED_SENSOR_SOURCE_KEY, _COMMISSIONED_SETTINGS_VERSION_KEY),
    )


def _load_object(payload_json: str) -> dict[str, object]:
    decoded = json.loads(payload_json)
    if not isinstance(decoded, dict):
        raise TypeError("stored JSON must be an object")
    return cast(dict[str, object], decoded)


def _load_settings(payload_json: str) -> SafetySettings:
    payload = _load_object(payload_json)
    version = _int_field(payload, "settings_version")
    if "forecast_threshold_c" not in payload:
        return SafetySettings(settings_version=version)
    return SafetySettings(
        protection_threshold_c=_float_field(payload, "protection_threshold_c"),
        release_threshold_c=_float_field(payload, "release_threshold_c"),
        forecast_threshold_c=_float_field(payload, "forecast_threshold_c"),
        forecast_days=_int_field(payload, "forecast_days"),
        sensor_stale_after_s=_int_field(payload, "sensor_stale_after_s"),
        forecast_stale_after_s=_int_field(payload, "forecast_stale_after_s"),
        timed_shower_default_s=_int_field(payload, "timed_shower_default_s"),
        timed_shower_max_s=_int_field(payload, "timed_shower_max_s"),
        latitude=_optional_float_field(payload, "latitude"),
        longitude=_optional_float_field(payload, "longitude"),
        timezone=_str_field(payload, "timezone"),
        sensor_device_id=_optional_str_field(payload, "sensor_device_id"),
        sensor_commissioned=_bool_field(payload, "sensor_commissioned"),
        settings_version=version,
    )


def _load_forecast(payload_json: str) -> ForecastSnapshot:
    payload = _load_object(payload_json)
    dates = _date_tuple(payload, "dates")
    minima = _float_tuple(payload, "daily_minima_c")
    source = _optional_datetime_field(payload, "source_generated_at")
    return ForecastSnapshot(
        dates=dates,
        daily_minima_c=minima,
        source_generated_at=source,
        fetched_at=_datetime_field(payload, "fetched_at"),
        latitude=_float_field(payload, "latitude"),
        longitude=_float_field(payload, "longitude"),
    )


def _float_field(payload: dict[str, object], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} must be numeric")
    return float(value)


def _optional_float_field(payload: dict[str, object], name: str) -> float | None:
    if payload.get(name) is None:
        return None
    return _float_field(payload, name)


def _int_field(payload: dict[str, object], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _bool_field(payload: dict[str, object], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def _str_field(payload: dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be a non-empty string")
    return value


def _optional_str_field(payload: dict[str, object], name: str) -> str | None:
    if payload.get(name) is None:
        return None
    return _str_field(payload, name)


def _date_tuple(payload: dict[str, object], name: str) -> tuple[date, ...]:
    value = payload.get(name)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{name} must be a string list")
    return tuple(date.fromisoformat(item) for item in value)


def _float_tuple(payload: dict[str, object], name: str) -> tuple[float, ...]:
    value = payload.get(name)
    if not isinstance(value, list):
        raise TypeError(f"{name} must be a numeric list")
    return tuple(
        _float_field({"item": item}, "item")
        for item in value
    )


def _datetime_field(payload: dict[str, object], name: str) -> datetime:
    value = _str_field(payload, name)
    return datetime.fromisoformat(value)


def _optional_datetime_field(payload: dict[str, object], name: str) -> datetime | None:
    if payload.get(name) is None:
        return None
    return _datetime_field(payload, name)
