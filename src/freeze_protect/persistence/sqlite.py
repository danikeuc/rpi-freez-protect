from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import cast

from freeze_protect.domain.models import AuditEvent, SafetySettings


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
        return settings


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
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def _initialize(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
              version INTEGER NOT NULL,
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
            """
        )


def _load_object(payload_json: str) -> dict[str, object]:
    decoded = json.loads(payload_json)
    if not isinstance(decoded, dict):
        raise TypeError("stored JSON must be an object")
    return cast(dict[str, object], decoded)


def _load_settings(payload_json: str) -> SafetySettings:
    payload = _load_object(payload_json)
    return SafetySettings(
        protection_threshold_c=_float_field(payload, "protection_threshold_c"),
        release_threshold_c=_float_field(payload, "release_threshold_c"),
        release_days=_int_field(payload, "release_days"),
        sensor_stale_after_s=_int_field(payload, "sensor_stale_after_s"),
        minimum_protection_dwell_s=_int_field(
            payload,
            "minimum_protection_dwell_s",
        ),
        settings_version=_int_field(payload, "settings_version"),
    )


def _float_field(payload: dict[str, object], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} must be numeric")
    return float(value)


def _int_field(payload: dict[str, object], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value
